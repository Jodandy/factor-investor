"""create_dividends_total_returns_tables

Revision ID: b64355eee475
Revises: f881666290d2
Create Date: 2026-10-06 22:11:12.463499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b64355eee475'
down_revision: Union[str, None] = 'f881666290d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create dividends table
    op.create_table(
        'dividends',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('ex_date', sa.Date(), nullable=False),
        sa.Column('payment_date', sa.Date(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=24, scale=6), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=True),
        sa.Column('is_estimated_ex_date', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.ins_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'ex_date', name='uq_dividends_ins_ex')
    )
    op.create_index('ix_dividends_ins_id', 'dividends', ['instrument_id'])
    op.create_index('ix_dividends_ex_date', 'dividends', ['ex_date'])

    # Create total_returns table
    op.create_table(
        'total_returns',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('close_price', sa.Numeric(precision=24, scale=6), nullable=False),
        sa.Column('total_return_index', sa.Numeric(precision=24, scale=6), nullable=False),
        sa.Column('total_return_index_sek', sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column('dividend_on_date', sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.ins_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'date', name='uq_total_returns_ins_date')
    )
    op.create_index('ix_total_returns_ins_id', 'total_returns', ['instrument_id'])
    op.create_index('ix_total_returns_date', 'total_returns', ['date'])


def downgrade() -> None:
    op.drop_index('ix_total_returns_date', table_name='total_returns')
    op.drop_index('ix_total_returns_ins_id', table_name='total_returns')
    op.drop_table('total_returns')
    op.drop_index('ix_dividends_ex_date', table_name='dividends')
    op.drop_index('ix_dividends_ins_id', table_name='dividends')
    op.drop_table('dividends')
