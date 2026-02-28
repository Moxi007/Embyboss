from bot.sql_helper import Base, Session, engine
from sqlalchemy import Column, String, DateTime, Integer, select
from sqlalchemy import or_


class Emby2(Base):
    """
    emby表，tg主键，默认值lv，us，iv
    """
    __tablename__ = 'emby2'
    embyid = Column(String(255), primary_key=True, autoincrement=False)
    name = Column(String(255), nullable=True)
    pwd = Column(String(255), nullable=True)
    pwd2 = Column(String(255), nullable=True)
    lv = Column(String(1), default='d')
    cr = Column(DateTime, nullable=True)
    ex = Column(DateTime, nullable=True)
    expired = Column(Integer, nullable=True)


async def sql_add_emby2(embyid, name, cr, ex, pwd='5210', pwd2='1234', lv='b', expired=0):
    """
    添加一条emby记录，如果tg已存在则忽略
    """
    async with Session() as session:
        try:
            emby = Emby2(embyid=embyid, name=name, pwd=pwd, pwd2=pwd2, lv=lv, cr=cr, ex=ex, expired=expired)
            session.add(emby)
            await session.commit()
        except:
            await session.rollback()


async def sql_get_emby2(name):
    """
    查询一条emby记录，可以根据, embyid或者name来查询
    """
    async with Session() as session:
        try:
            # 使用or_方法来表示或者的逻辑
            result = await session.execute(select(Emby2).filter(or_(Emby2.name == name, Emby2.embyid == name)))
            emby = result.scalars().first()
            if emby:
                session.expunge(emby)
            return emby
        except:
            return None


async def get_all_emby2(condition):
    """
    查询所有emby记录
    """
    async with Session() as session:
        try:
            result = await session.execute(select(Emby2).filter(condition))
            embies = result.scalars().all()
            for e in embies:
                session.expunge(e)
            return embies
        except:
            return None


async def sql_update_emby2(condition, **kwargs):
    """
    更新一条emby记录，根据condition来匹配，然后更新其他的字段
    """
    async with Session() as session:
        try:
            # 用filter来过滤
            result = await session.execute(select(Emby2).filter(condition))
            emby = result.scalars().first()
            if emby is None:
                return False
            # 然后用setattr方法来更新其他的字段
            for k, v in kwargs.items():
                setattr(emby, k, v)
            await session.commit()
            return True
        except:
            await session.rollback()
            return False


async def sql_delete_emby2(embyid):
    """
    根据embyid删除一条emby记录
    """
    async with Session() as session:
        try:
            result = await session.execute(select(Emby2).filter_by(embyid=embyid))
            emby = result.scalars().first()
            if emby:
                await session.delete(emby)
                try:
                    await session.commit()
                    return True
                except Exception as e:
                    # 记录错误信息
                    print(e)
                    # 回滚事务
                    await session.rollback()
                    return False
            else:
                return None
        except Exception as e:
            # 记录错误信息
            print(e)
            await session.rollback()
            return False

async def sql_delete_emby2_by_name(name):
    """
    根据name删除一条emby记录
    """
    async with Session() as session:
        try:
            result = await session.execute(select(Emby2).filter_by(name=name))
            emby = result.scalars().first()
            if emby:
                await session.delete(emby)
                await session.commit()
                return True
            else:
                return False
        except Exception as e:
            # 记录错误信息
            print(e)
            await session.rollback()
            return False

