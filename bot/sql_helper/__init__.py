"""
初始化数据库（异步重构版）
"""
import asyncio
from bot import LOGGER, config
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# 创建异步 engine 对象 (使用 aiomysql 驱动)
engine = create_async_engine(
    f"mysql+aiomysql://{config.db_user}:{config.db_pwd}@{config.db_host}:{config.db_port}/{config.db_name}?charset=utf8mb4",
    echo=False,
    echo_pool=False,
    pool_size=16,
    pool_recycle=60 * 30,
)

# 创建Base对象
Base = declarative_base()
# 异步引擎下不能直接 bind=engine，需要在初始化表时绑定

# 创建异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# 提供一个类似之前上下文使用的Session对象或工厂
# 注意：在异步环境下，应使用 async with AsyncSessionLocal() as session:
Session = AsyncSessionLocal

async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        LOGGER.info("数据库表结构初始化成功")
    except Exception as e:
        LOGGER.error(f"数据库表结构初始化失败: {e}")

