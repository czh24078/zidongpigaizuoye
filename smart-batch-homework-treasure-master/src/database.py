from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config import config

engine = create_async_engine(
    config.database_url(),
    echo=config.DEBUG,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    from src.models.db_models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
