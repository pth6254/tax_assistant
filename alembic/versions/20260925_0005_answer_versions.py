"""Preserve every regenerated assistant answer for the last conversation turn."""
from alembic import op

revision = '20260925_0005'
down_revision = '20260924_0004'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        ALTER TABLE chat_logs ADD COLUMN answer_version integer NOT NULL DEFAULT 1;
        CREATE TABLE chat_answer_versions (
            assistant_message_id bigint NOT NULL REFERENCES chat_logs(id) ON DELETE CASCADE,
            version integer NOT NULL CHECK (version >= 1),
            message jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (assistant_message_id, version)
        );
    ''')


def downgrade():
    op.execute('DROP TABLE chat_answer_versions; ALTER TABLE chat_logs DROP COLUMN answer_version;')
