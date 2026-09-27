"""Allow the five existing calculator types in consultation cases."""
from alembic import op

revision = '20260926_0007'
down_revision = '20260926_0006'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE consultation_cases DROP CONSTRAINT consultation_cases_kind_check")
    op.execute("""ALTER TABLE consultation_cases ADD CONSTRAINT consultation_cases_kind_check
        CHECK (kind IN ('income_tax','capital_gains','inheritance','gift','vat','penalty_tax'))""")
    op.execute("ALTER TABLE consultation_cases ADD COLUMN reference_date date")
    op.execute("UPDATE consultation_cases SET reference_date=make_date(tax_year,12,31)")
    op.execute("ALTER TABLE consultation_cases ALTER COLUMN reference_date SET NOT NULL")


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM consultation_cases WHERE kind <> 'income_tax') THEN
            RAISE EXCEPTION 'Cannot downgrade consultation kinds while non-income cases exist';
        END IF;
    END $$""")
    op.execute("ALTER TABLE consultation_cases DROP CONSTRAINT consultation_cases_kind_check")
    op.execute("""ALTER TABLE consultation_cases ADD CONSTRAINT consultation_cases_kind_check
        CHECK (kind = 'income_tax')""")
    op.execute("ALTER TABLE consultation_cases DROP COLUMN reference_date")
