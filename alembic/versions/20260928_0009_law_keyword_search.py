"""Index official law title and text for bounded Korean keyword retrieval."""
from alembic import op

revision = '20260928_0009'
down_revision = '20260926_0008'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute('''CREATE INDEX IF NOT EXISTS law_articles_title_trgm_idx
                  ON law_articles USING gin (article_title gin_trgm_ops)
                  WHERE is_current = TRUE''')
    op.execute('''CREATE INDEX IF NOT EXISTS law_articles_text_trgm_idx
                  ON law_articles USING gin (article_text gin_trgm_ops)
                  WHERE is_current = TRUE''')


def downgrade():
    op.execute('DROP INDEX IF EXISTS law_articles_text_trgm_idx')
    op.execute('DROP INDEX IF EXISTS law_articles_title_trgm_idx')
