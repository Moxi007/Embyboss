"""
基本的sql操作 (异步重构版)
"""
from bot.sql_helper import Base, Session, engine
from sqlalchemy import Column, BigInteger, String, DateTime, Integer, case, select, update, delete, func
from sqlalchemy import or_, text
from bot import LOGGER

class Emby(Base):
    """
    emby表，tg主键，默认值lv，us，iv
    """
    __tablename__ = 'emby'
    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    embyid = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    pwd = Column(String(255), nullable=True)
    pwd2 = Column(String(255), nullable=True)
    lv = Column(String(1), default='d')
    cr = Column(DateTime, nullable=True)
    ex = Column(DateTime, nullable=True)
    us = Column(Integer, default=0)
    iv = Column(Integer, default=0)
    ch = Column(DateTime, nullable=True)
    game_played = Column(Integer, default=0)  # 参与游戏总场次
    game_won = Column(Integer, default=0)     # 获胜游戏场次

async def migrate_add_game_stats_fields():
    """
    数据库迁移：添加游戏统计字段
    在系统启动时自动执行，检查并添加 game_played 和 game_won 字段
    """
    async with Session() as session:
        try:
            # 检查字段是否存在
            result = await session.execute(text(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'emby'"
            ))
            existing_columns = {row[0] for row in result}
            
            # 添加 game_played 字段
            if 'game_played' not in existing_columns:
                LOGGER.info("检测到 game_played 字段不存在，开始添加...")
                try:
                    await session.execute(text("ALTER TABLE emby ADD COLUMN game_played INT DEFAULT 0 NOT NULL"))
                    await session.commit()
                    LOGGER.info("成功添加 game_played 字段")
                except Exception as e:
                    LOGGER.error(f"添加 game_played 字段失败: {e}")
                    await session.rollback()
            else:
                LOGGER.info("game_played 字段已存在，跳过迁移")
            
            # 添加 game_won 字段
            if 'game_won' not in existing_columns:
                LOGGER.info("检测到 game_won 字段不存在，开始添加...")
                try:
                    await session.execute(text("ALTER TABLE emby ADD COLUMN game_won INT DEFAULT 0 NOT NULL"))
                    await session.commit()
                    LOGGER.info("成功添加 game_won 字段")
                except Exception as e:
                    LOGGER.error(f"添加 game_won 字段失败: {e}")
                    await session.rollback()
            else:
                LOGGER.info("game_won 字段已存在，跳过迁移")
            
            LOGGER.info("数据库迁移完成")
            return True
            
        except Exception as e:
            LOGGER.error(f"数据库迁移失败: {e}")
            await session.rollback()
            # 迁移失败不中断系统启动
            return False


async def sql_add_emby(tg: int):
    """
    添加一条emby记录，如果tg已存在则忽略
    """
    async with Session() as session:
        try:
            emby = Emby(tg=tg)
            session.add(emby)
            await session.commit()
        except Exception as e:
            await session.rollback()

async def sql_delete_emby_by_tg(tg):
    """
    根据tg删除一条emby记录
    """
    async with Session() as session:
        try:
            result = await session.execute(select(Emby).filter(Emby.tg == tg))
            emby = result.scalars().first()
            if emby:
                await session.delete(emby)
                await session.commit()
                LOGGER.info(f"删除数据库记录成功 {tg}")
                return True
            else:
                LOGGER.info(f"数据库记录不存在 {tg}")
                return False
        except Exception as e:
            LOGGER.error(f"删除数据库记录时发生异常 {e}")
            await session.rollback()
            return False

async def sql_clear_emby_iv():
    """
    清除所有emby的iv
    """
    async with Session() as session:
        try:
            await session.execute(update(Emby).values(iv=0))
            await session.commit()
            return True
        except Exception as e:
            LOGGER.error(f"清除所有emby的iv时发生异常 {e}")
            await session.rollback()
            return False

async def sql_delete_emby(tg=None, embyid=None, name=None):
    """
    根据tg, embyid或name删除一条emby记录
    至少需要提供一个参数，如果所有参数都为None，则返回False
    """
    async with Session() as session:
        try:
            # 构建条件列表，只包含非None的参数
            conditions = []
            if tg is not None:
                conditions.append(Emby.tg == tg)
            if embyid is not None:
                conditions.append(Emby.embyid == embyid)
            if name is not None:
                conditions.append(Emby.name == name)
            
            # 如果所有参数都为None，返回False
            if not conditions:
                LOGGER.warning("sql_delete_emby: 所有参数都为None，无法删除记录")
                return False
            
            # 使用or_组合所有条件
            condition = or_(*conditions)
            LOGGER.debug(f"删除数据库记录，条件: tg={tg}, embyid={embyid}, name={name}")
            
            # 用filter来过滤，使用with_for_update锁定记录
            result = await session.execute(select(Emby).filter(condition).with_for_update())
            emby = result.scalars().first()
            if emby:
                LOGGER.info(f"删除数据库记录 {emby.name} - {emby.embyid} - {emby.tg}")
                await session.delete(emby)
                try:
                    await session.commit()
                    LOGGER.info(f"成功删除数据库记录: tg={tg}, embyid={embyid}, name={name}")
                    return True
                except Exception as e:
                    LOGGER.error(f"删除数据库记录时提交事务失败 {e}")
                    await session.rollback()
                    return False
            else:
                LOGGER.info(f"数据库记录不存在: tg={tg}, embyid={embyid}, name={name}")
                return False
        except Exception as e:
            LOGGER.error(f"删除数据库记录时发生异常 {e}")
            await session.rollback()
            return False


async def sql_update_embys(some_list: list, method=None):
    """ 根据list中的tg值批量更新一些值 ，此方法不可更新主键"""
    # Note: async bulk update has some differences in syntax or can be done iteratively. 
    # For simplicity and correctness with async drivers, we do it mapped.
    # In sqlalchemy 2.0 async, `session.bulk_update_mappings` isn't fully supported natively the same way, best is executing an update statement directly or updating in a loop.
    async with Session() as session:
        try:
            if method == 'iv':
                for c in some_list:
                    await session.execute(update(Emby).where(Emby.tg == c[0]).values(iv=c[1]))
            elif method == 'ex':
                for c in some_list:
                    await session.execute(update(Emby).where(Emby.tg == c[0]).values(ex=c[1]))
            elif method == 'bind':
                for c in some_list:
                    await session.execute(update(Emby).where(Emby.tg == c[0]).values(name=c[1], embyid=c[2]))
            await session.commit()
            return True
        except Exception as e:
            LOGGER.error(f"批量更新异常: {e}")
            await session.rollback()
            return False


async def sql_get_emby(tg):
    """
    查询一条emby记录，可以根据tg, embyid或者name来查询
    """
    async with Session() as session:
        try:
            # 使用or_方法来表示或者的逻辑
            result = await session.execute(select(Emby).filter(or_(Emby.tg == tg, Emby.name == tg, Emby.embyid == tg)))
            emby = result.scalars().first()
            # async session doesn't keep objects bound after session close, so we need to expunge if we want to use them
            if emby:
                session.expunge(emby)
            return emby
        except Exception as e:
            LOGGER.error(f"查询emby失败: {e}")
            return None


async def get_all_emby(condition):
    """
    查询所有emby记录
    """
    async with Session() as session:
        try:
            result = await session.execute(select(Emby).filter(condition))
            embies = result.scalars().all()
            for e in embies:
                session.expunge(e)
            return embies
        except Exception as e:
            LOGGER.error(f"获取所有emby失败: {e}")
            return None


async def sql_update_emby(condition, **kwargs):
    """
    更新一条emby记录，根据condition来匹配，然后更新其他的字段
    """
    async with Session() as session:
        try:
            # 用filter来过滤
            result = await session.execute(select(Emby).filter(condition))
            emby = result.scalars().first()
            if emby is None:
                return False
            # 然后用setattr方法来更新其他的字段
            for k, v in kwargs.items():
                setattr(emby, k, v)
            await session.commit()
            return True
        except Exception as e:
            LOGGER.error(f"更新emby失败: {e}")
            await session.rollback()
            return False

async def sql_count_emby():
    """
    # 检索有tg和embyid的emby记录的数量，以及Emby.lv =='a'条件下的数量
    # count = await sql_count_emby()
    :return: int, int, int
    """
    async with Session() as session:
        try:
            # 使用func.count来计算数量
            stmt = select(
                func.count(Emby.tg).label("tg_count"),
                func.count(Emby.embyid).label("embyid_count"),
                func.count(case((Emby.lv == "a", 1))).label("lv_a_count")
            )
            result = await session.execute(stmt)
            count = result.first()
            return count.tg_count, count.embyid_count, count.lv_a_count
        except Exception as e:
            LOGGER.error(f"查询emby数量统计失败: {e}")
            return None, None, None

