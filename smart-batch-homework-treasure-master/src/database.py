from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config import config

engine = create_async_engine(
    config.database_url(),
    echo=config.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    connect_args={"charset": "utf8mb4"},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    from src.models.db_models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_bank_no)
        await conn.run_sync(_migrate_subject)


def _migrate_bank_no(conn) -> None:
    """为 question_bank 表添加 bank_no 列，并按 added_at 顺序分配序号。"""
    rows = conn.exec_driver_sql(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'question_bank' "
        "AND COLUMN_NAME = 'bank_no'"
    ).fetchall()
    if rows[0][0] > 0:
        return
    conn.exec_driver_sql("ALTER TABLE question_bank ADD COLUMN bank_no INT")
    rows = conn.exec_driver_sql(
        "SELECT id FROM question_bank ORDER BY added_at ASC"
    ).fetchall()
    for i, (row_id,) in enumerate(rows, start=1):
        conn.exec_driver_sql(
            "UPDATE question_bank SET bank_no = :no WHERE id = :rid",
            {"no": i, "rid": row_id},
        )


def _migrate_subject(conn) -> None:
    """为 question_bank 和 questions 表添加 subject 列（如果尚不存在）。"""
    for table in ("question_bank", "questions"):
        rows = conn.exec_driver_sql(
            f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}' "
            f"AND COLUMN_NAME = 'subject'",
        ).fetchall()
        if rows[0][0] > 0:
            continue
        conn.exec_driver_sql(
            f"ALTER TABLE `{table}` ADD COLUMN `subject` VARCHAR(20) NOT NULL DEFAULT '其他'"
        )
