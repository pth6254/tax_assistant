"""Record each accepted chat question so daily limits can be enforced (usage_limits.py)."""
from alembic import op

revision = '20261023_0024'
down_revision = '20261012_0023'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS chat_usage (
        id bigserial PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind text NOT NULL CHECK (kind IN ('question', 'regeneration')),
        created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS chat_usage_user_time ON chat_usage (user_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS chat_usage_time ON chat_usage (created_at)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS chat_usage")
