"""Document review, consultation scenarios, and personal calendar tracking."""
from alembic import op

revision = '20260926_0008'
down_revision = '20260926_0007'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
    CREATE TABLE user_document_files (
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        filename text NOT NULL,
        content bytea NOT NULL,
        sha256 text NOT NULL,
        uploaded_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, filename)
    );
    CREATE TABLE user_document_reviews (
        user_id uuid NOT NULL,
        filename text NOT NULL,
        document_sha256 text NOT NULL,
        fields jsonb NOT NULL DEFAULT '{}'::jsonb,
        reviewed_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (user_id, filename),
        FOREIGN KEY (user_id, filename) REFERENCES user_document_files(user_id, filename)
            ON DELETE CASCADE
    );
    CREATE TABLE consultation_scenarios (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        case_id uuid NOT NULL REFERENCES consultation_cases(id) ON DELETE CASCADE,
        name text NOT NULL,
        kind text NOT NULL,
        reference_date date NOT NULL,
        facts jsonb NOT NULL,
        result jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX consultation_scenarios_case_idx ON consultation_scenarios(user_id, case_id, created_at DESC);
    CREATE TABLE personal_tax_events (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        due_date date NOT NULL,
        title text NOT NULL,
        note text NOT NULL DEFAULT '',
        source_url text NOT NULL,
        status text NOT NULL DEFAULT 'watching'
            CHECK (status IN ('watching','preparing','done','not_applicable')),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (user_id, due_date, title)
    );
    CREATE INDEX personal_tax_events_user_due_idx ON personal_tax_events(user_id, due_date);
    ''')


def downgrade():
    op.execute('DROP TABLE personal_tax_events')
    op.execute('DROP TABLE consultation_scenarios')
    op.execute('DROP TABLE user_document_reviews')
    op.execute('DROP TABLE user_document_files')
