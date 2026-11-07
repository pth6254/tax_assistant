"""The date from which a current article's wording has been in force (docs/ai/DATA_STRATEGY.md).

effective_date names the version a row was taken from; an article whose wording did not change keeps
governing events back to the first version with that wording. The event-date check uses this date, so a
newer version label no longer narrows what the current text can answer for.
"""
from alembic import op

revision = '20261107_0025'
down_revision = '20261023_0024'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE law_articles ADD COLUMN IF NOT EXISTS in_force_since text")


def downgrade():
    op.execute("ALTER TABLE law_articles DROP COLUMN IF EXISTS in_force_since")
