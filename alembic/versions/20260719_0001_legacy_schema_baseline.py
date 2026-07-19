"""Bootstrap the complete schema and adopt existing legacy databases.

Revision ID: 20260719_0001
Revises: None
"""
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260719_0001"
down_revision = None
branch_labels = None
depends_on = None

ROOT = Path(__file__).resolve().parents[2]


def _exists(kind: str, name: str) -> bool:
    bind = op.get_bind()
    sql = sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema."
        + ("tables" if kind == "table" else "columns")
        + " WHERE table_schema = 'public' AND "
        + ("table_name = :name" if kind == "table" else "table_name = :table AND column_name = :name")
        + ")"
    )
    params = {"name": name}
    if kind != "table":
        table, column = name.split(".", 1)
        params = {"table": table, "name": column}
    return bool(bind.execute(sql, params).scalar())


def _run_sql(relative_path: str) -> None:
    sql = (ROOT / relative_path).read_text(encoding="utf-8")
    # psycopg supports PostgreSQL multi-statement scripts. Alembic's transaction
    # still owns commit/rollback, so a failed legacy script is applied atomically.
    driver_connection = op.get_bind().connection.driver_connection
    driver_connection.execute(sql)


def upgrade() -> None:
    # Very early databases had documents without a timestamp.  Repair the
    # column before init.sql creates the (user_id, created_at) index.
    if _exists("table", "documents") and not _exists("column", "documents.created_at"):
        op.execute(
            "ALTER TABLE documents ADD COLUMN created_at TIMESTAMPTZ "
            "NOT NULL DEFAULT now()"
        )

    # A database without the legacy root table is a fresh installation. Existing
    # databases skip init.sql because it still contains pre-conversation indexes
    # that refer to chat_logs.session_id.
    if not _exists("table", "users"):
        _run_sql("db/init.sql")

    # Seed scripts are intentionally run only when their target tables/data do not
    # exist, preventing duplicate tax rows when adopting an existing database.
    if not _exists("table", "tax_brackets"):
        _run_sql("db/migrations/001_tax_calculator.sql")

    _run_sql("db/migrations/002_user_profile.sql")

    if not _exists("table", "conversations"):
        _run_sql("db/migrations/003_conversations.sql")
    else:
        # Handle a partially applied legacy migration without truncating chat data.
        if _exists("column", "chat_logs.session_id") and not _exists("column", "chat_logs.conversation_id"):
            op.execute("ALTER TABLE chat_logs RENAME COLUMN session_id TO conversation_id")
        op.execute("DROP INDEX IF EXISTS chat_logs_session_idx")
        op.execute(
            "CREATE INDEX IF NOT EXISTS chat_logs_conversation_idx "
            "ON chat_logs (conversation_id, created_at DESC)"
        )

    _run_sql("db/migrations/004_fix_inheritance_gift_tax_law_name.sql")
    _run_sql("db/migrations/005_business_type.sql")
    _run_sql("db/migrations/006_law_article_clauses.sql")

    vat_exists = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM tax_brackets WHERE tax_type = '부가가치세')")
    ).scalar()
    penalty_exists = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM tax_deductions WHERE tax_type = '가산세')")
    ).scalar()
    if not vat_exists and not penalty_exists:
        _run_sql("db/migrations/007_vat_penalty_seed.sql")


def downgrade() -> None:
    # This baseline adopts databases that may contain production/user data.
    # Destructive downgrade is deliberately unsupported.
    raise RuntimeError("The legacy baseline cannot be downgraded safely.")
