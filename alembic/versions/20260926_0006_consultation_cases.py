"""Store user-owned income-tax consultation workspaces."""
from alembic import op

revision = '20260926_0006'
down_revision = '20260925_0005'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE TABLE consultation_cases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id uuid UNIQUE REFERENCES conversations(id) ON DELETE SET NULL,
            kind text NOT NULL DEFAULT 'income_tax' CHECK (kind = 'income_tax'),
            title text NOT NULL,
            question text NOT NULL,
            tax_year integer NOT NULL CHECK (tax_year BETWEEN 2000 AND 2100),
            facts jsonb NOT NULL DEFAULT '{}'::jsonb,
            checklist jsonb NOT NULL DEFAULT '{}'::jsonb,
            calculation jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX consultation_cases_user_updated_idx
            ON consultation_cases (user_id, updated_at DESC);
    ''')


def downgrade():
    op.execute('DROP TABLE consultation_cases;')
