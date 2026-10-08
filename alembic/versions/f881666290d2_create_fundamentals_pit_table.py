"""create fundamentals_pit table

Revision ID: f881666290d2
Revises: b22cf4aa60b6
Create Date: 2026-10-06 21:24:22.688609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f881666290d2'
down_revision: Union[str, None] = 'b22cf4aa60b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create fundamentals_pit table
    op.create_table(
        'fundamentals_pit',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('metric', sa.String(length=100), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('period_type', sa.String(length=10), nullable=False),
        sa.Column('value', sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column('known_from', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.ins_id'], name='fk_fundamentals_pit_instrument'),
        sa.PrimaryKeyConstraint('id', name='pk_fundamentals_pit'),
        sa.UniqueConstraint('instrument_id', 'metric', 'period_end', 'period_type', 'known_from',
                           name='uq_fundamentals_pit')
    )

    # Create indexes for efficient as_of() queries
    op.create_index(
        'ix_fundamentals_pit_as_of',
        'fundamentals_pit',
        ['instrument_id', 'metric', 'known_from', sa.text('period_end DESC')]
    )
    op.create_index('ix_fundamentals_pit_period', 'fundamentals_pit', ['period_end'])
    op.create_index('ix_fundamentals_pit_metric', 'fundamentals_pit', ['metric'])


def downgrade() -> None:
    op.drop_index('ix_fundamentals_pit_metric', table_name='fundamentals_pit')
    op.drop_index('ix_fundamentals_pit_period', table_name='fundamentals_pit')
    op.drop_index('ix_fundamentals_pit_as_of', table_name='fundamentals_pit')
    op.drop_table('fundamentals_pit')
