"""Persist explicit skipped-question outcomes.

Revision ID: 20261111_0005
Revises: 20261111_0004
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261111_0005"
down_revision: str | None = "20261111_0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "interview_questions",
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("interview_questions", "skipped")
