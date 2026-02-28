import math

from bot.sql_helper import Base, Session, engine
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    DateTime,
    Integer,
    or_,
    and_,
    case,
    func,
    select,
    update,
    delete
)
from cacheout import Cache

cache = Cache()


class Code(Base):
    """
    register_code表，code主键，tg,us,used,used_time
    """

    __tablename__ = "Rcode"
    code = Column(String(50), primary_key=True, autoincrement=False)
    tg = Column(BigInteger)
    us = Column(Integer)
    used = Column(BigInteger, nullable=True)
    usedtime = Column(DateTime, nullable=True)


async def sql_add_code(code_list: list, tg: int, us: int):
    """批量添加记录，如果code已存在则忽略"""
    async with Session() as session:
        try:
            codes = [Code(code=c, tg=tg, us=us) for c in code_list]
            session.add_all(codes)
            await session.commit()
            return True
        except:
            await session.rollback()
            return False


async def sql_update_code(code, used: int, usedtime):
    async with Session() as session:
        try:
            data = {"used": used, "usedtime": usedtime}
            stmt = update(Code).where(Code.code == code).values(data)
            result = await session.execute(stmt)
            if result.rowcount == 0:
                return False
            await session.commit()
            return True
        except Exception as e:
            print(e)
            await session.rollback()
            return False


async def sql_get_code(code):
    async with Session() as session:
        try:
            result = await session.execute(select(Code).filter(Code.code == code))
            c = result.scalars().first()
            if c:
                session.expunge(c)
            return c
        except:
            return None


async def sql_count_code(tg: int = None):
    async with Session() as session:
        if tg is None:
            try:
                # 查询used不为空的数量
                used_count = await session.scalar(select(func.count()).filter(Code.used != None))
                # 查询所有未使用的数量
                unused_count = await session.scalar(select(func.count()).filter(Code.used == None))
                # 查询used为空时，us=30，90，180，360的数量
                us_list = [30, 90, 180, 365]  # 创建一个列表，存储us的值
                counts = []
                for us in us_list:
                    count = await session.scalar(select(func.count()).filter(Code.used == None).filter(Code.us == us))
                    counts.append(count)
                
                tg_mon, tg_sea, tg_half, tg_year = counts
                return used_count, tg_mon, tg_sea, tg_half, tg_year, unused_count
            except Exception as e:
                print(e)
                return None
        else:
            try:
                used_count = await session.scalar(select(func.count()).filter(Code.used != None).filter(Code.tg == tg))
                unused_count = await session.scalar(select(func.count()).filter(Code.used == None).filter(Code.tg == tg))
                us_list = [30, 90, 180, 365]
                counts = []
                for us in us_list:
                    count = await session.scalar(select(func.count()).filter(Code.used == None).filter(Code.us == us).filter(Code.tg == tg))
                    counts.append(count)
                tg_mon, tg_sea, tg_half, tg_year = counts
                return used_count, tg_mon, tg_sea, tg_half, tg_year, unused_count
            except Exception as e:
                print(e)
                return None


async def sql_count_p_code(tg_id, us, page: int = 1):
    async with Session() as session:
        try:
            if us == 0:
                p = await session.scalar(select(func.count()).filter(Code.used != None).filter(Code.tg == tg_id))
            elif us == -1:
                p = await session.scalar(select(func.count()).filter(Code.used == None).filter(Code.tg == tg_id))
            else:
                p = await session.scalar(select(func.count()).filter(Code.us == us).filter(Code.tg == tg_id))
            
            if p == 0:
                return None, 1
            i = math.ceil(p / 30)
            
            if page < 1:
                page = 1
            elif page > i:
                page = i
                
            d = (page - 1) * 30
            if us == -1:
                stmt = (
                    select(Code.tg, Code.code, Code.used, Code.usedtime, Code.us)
                    .filter(Code.used == None)
                    .filter(Code.tg == tg_id)
                    .order_by(Code.us.asc())
                    .limit(30)
                    .offset(d)
                )
            elif us != 0:
                # 查询us和tg匹配的记录，按tg升序，usedtime降序排序，分页查询
                stmt = (
                    select(Code.tg, Code.code, Code.used, Code.usedtime, Code.us)
                    .filter(Code.us == us)
                    .filter(Code.tg == tg_id)
                    .filter(Code.used == None)
                    .order_by(Code.tg.asc(), Code.usedtime.desc())
                    .limit(30)
                    .offset(d)
                )
            else:
                stmt = (
                    select(Code.tg, Code.code, Code.used, Code.usedtime, Code.us)
                    .filter(Code.used != None)
                    .filter(Code.tg == tg_id)
                    .order_by(Code.tg.asc(), Code.usedtime.desc())
                    .limit(30)
                    .offset(d)
                )
            result = await session.execute(stmt)
            rows = result.all()
            x = ""
            e = 1 if d == 0 else d + 1
            for link in rows:
                if us == 0:
                    c = (
                        f"{e}. `"
                        + f"{link.code}`"
                        + f"\n🎁 {link.us}d - [{link.used}](tg://user?id={link.tg})(__{link.usedtime}__)\n"
                    )
                else:
                    c = f"{e}. `" + f"{link.code}`\n"
                x += c
                e += 1
            return x, i
        except Exception as e:
            # 查询失败时，打印异常信息，并返回None
            print(e)
            return None, 1


async def sql_count_c_code(tg_id, page: int = 1):
    async with Session() as session:
        try:
            p = await session.scalar(select(func.count()).filter(Code.tg == tg_id))
            if p == 0:
                return None, 1
            i = math.ceil(p / 5)
            
            if page < 1:
                page = 1
            elif page > i:
                page = i
                
            d = (page - 1) * 5
            stmt = (
                select(Code.tg, Code.code, Code.used, Code.usedtime, Code.us)
                .filter(Code.tg == tg_id)
                .order_by(Code.tg.asc(), Code.usedtime.desc())
                .limit(5)
                .offset(d)
            )
            result = await session.execute(stmt)
            rows = result.all()
            x = ""
            e = 1 if d == 0 else d + 1
            for link in rows:
                c = (
                    f"{e}. `{link.code}`\n"
                    f"🎁： {link.us} 天 | 👤[{link.used}](tg://user?id={link.used})\n"
                    f"🌏：{link.usedtime}\n\n"
                )
                x += c
                e += 1
            # x 是当前页内容，i是总页数
            return x, i
        except Exception as e:
            # 查询失败时，打印异常信息，并返回None
            print(e)
            return None, 1

async def sql_delete_unused_by_days(days: list[int], user_id: int = None) -> int:
    async with Session() as session:
        try:
            stmt = delete(Code).where(Code.used == None).where(Code.us.in_(days))
            if user_id is not None:
                stmt = stmt.where(Code.tg == user_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
        except Exception as e:
            await session.rollback()
            print(f"删除注册码失败: {e}")
            return 0


async def sql_delete_all_unused(user_id: int = None) -> int:
    async with Session() as session:
        try:
            stmt = delete(Code).where(Code.used == None)
            if user_id is not None:
                stmt = stmt.where(Code.tg == user_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
        except Exception as e:
            await session.rollback()
            print(f"删除所有未使用注册码失败: {e}")
            return 0
