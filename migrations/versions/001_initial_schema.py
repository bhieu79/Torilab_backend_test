"""Initial schema

Revision ID: 001
Create Date: 2025-05-13 11:02:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Create tables
    op.create_table(
        'clients',
        sa.Column('client_id', sa.String(), primary_key=True),
        sa.Column('timezone', sa.String(), nullable=False)
    )

    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.String(), sa.ForeignKey('clients.client_id'), nullable=False),
        sa.Column('message_type', sa.String(5), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('client_timestamp', sa.DateTime(), nullable=False),
        sa.Column('is_accepted', sa.Boolean(), nullable=False),
        sa.Column('timezone', sa.String(), nullable=False, server_default='UTC'),
        sa.Column('status_message', sa.String())
    )

    op.create_table(
        'replies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('message_id', sa.Integer(), sa.ForeignKey('messages.id'), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('reply_type', sa.String(), nullable=False),
        sa.Column('is_delivered', sa.Boolean(), nullable=False, server_default='0')
    )

def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table('replies')
    op.drop_table('messages')
    op.drop_table('clients')