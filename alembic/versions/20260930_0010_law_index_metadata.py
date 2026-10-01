"""Record the original and input used to build law vectors."""
from alembic import op

revision = '20260930_0010'
down_revision = '20260928_0009'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE law_articles ADD COLUMN index_metadata jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE law_article_clauses ADD COLUMN index_metadata jsonb NOT NULL DEFAULT '{}'::jsonb")


def downgrade():
    op.execute('ALTER TABLE law_article_clauses DROP COLUMN index_metadata')
    op.execute('ALTER TABLE law_articles DROP COLUMN index_metadata')
