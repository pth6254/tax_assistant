"""Tie conversations, their messages and uploaded chunks to their owner.

`conversations.user_id`, `documents.user_id` and `chat_logs.conversation_id` had no foreign
key, so deleting an account or a conversation in several statements could leave rows behind.
On 2026-10-12 the development database held 644 messages of 322 missing conversations
(written 2026-07-11..19), 5 conversations and 5 document chunks of deleted users.

Those rows are first copied to `orphan_backup_*` tables (they stay after a downgrade), then
removed, and the keys are added with ON DELETE CASCADE: deleting a user removes everything
the user owns, and deleting a conversation removes its messages.
"""
from alembic import op

revision = '20261012_0023'
down_revision = '20261012_0022'
branch_labels = None
depends_on = None

ORPHAN_CONVERSATIONS = "NOT EXISTS (SELECT 1 FROM users u WHERE u.id = conversations.user_id)"


def upgrade():
    op.execute(f"""CREATE TABLE IF NOT EXISTS orphan_backup_conversations AS
        SELECT * FROM conversations WHERE {ORPHAN_CONVERSATIONS}""")
    op.execute(f"""CREATE TABLE IF NOT EXISTS orphan_backup_chat_logs AS
        SELECT * FROM chat_logs l WHERE NOT EXISTS (SELECT 1 FROM conversations c WHERE c.id = l.conversation_id)
           OR l.conversation_id IN (SELECT id FROM conversations WHERE {ORPHAN_CONVERSATIONS})""")
    op.execute("""CREATE TABLE IF NOT EXISTS orphan_backup_documents AS
        SELECT * FROM documents d WHERE d.user_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = d.user_id)""")
    op.execute("DELETE FROM chat_logs l WHERE l.id IN (SELECT id FROM orphan_backup_chat_logs)")
    op.execute(f"DELETE FROM conversations WHERE {ORPHAN_CONVERSATIONS}")
    op.execute("DELETE FROM documents d WHERE d.id IN (SELECT id FROM orphan_backup_documents)")
    op.execute("""ALTER TABLE chat_logs ADD CONSTRAINT chat_logs_conversation_id_fkey
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE""")
    op.execute("""ALTER TABLE conversations ADD CONSTRAINT conversations_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE""")
    op.execute("""ALTER TABLE documents ADD CONSTRAINT documents_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE""")


def downgrade():
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_user_id_fkey")
    op.execute("ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_user_id_fkey")
    op.execute("ALTER TABLE chat_logs DROP CONSTRAINT IF EXISTS chat_logs_conversation_id_fkey")
