"""add fastapi users columns

Revision ID: add_fusers_cols
Revises: c782351e96b9
Create Date: 2026-05-19 17:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_fusers_cols'
down_revision: Union[str, Sequence[str], None] = 'c782351e96b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add columns with server default to guarantee existing rows get valid values
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('users', sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.text('false')))

def downgrade() -> None:
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'is_verified')
    op.drop_column('users', 'is_superuser')
