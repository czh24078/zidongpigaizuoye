from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config import config

engine = create_async_engine(
    config.database_url(),
    echo=config.DEBUG,
    connect_args={"check_same_thread": False, "timeout": 15},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    from src.models.db_models import Base
    async with engine.begin() as conn:
        # 开启 WAL 模式（读写并发） + 设置忙等超时
        await conn.run_sync(lambda sync_conn: sync_conn.exec_driver_sql("PRAGMA journal_mode=WAL"))
        await conn.run_sync(lambda sync_conn: sync_conn.exec_driver_sql("PRAGMA busy_timeout=5000"))
        await conn.run_sync(Base.metadata.create_all)
