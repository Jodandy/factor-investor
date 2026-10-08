"""create_universe_corporate_events_tables

Revision ID: fc9758212f12
Revises: b64355eee475
Create Date: 2026-10-06 22:30:10.763485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc9758212f12'
down_revision: Union[str, None] = 'b64355eee475'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create universe_constituents table
    op.create_table(
        'universe_constituents',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('market_cap_local', sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column('median_turnover_60d', sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column('price', sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column('years_of_history', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('is_eligible', sa.Boolean(), nullable=False),
        sa.Column('exclusion_reason', sa.String(length=200), nullable=True),
        sa.Column('liquidity_bucket', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.ins_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'date', name='uq_universe_ins_date')
    )
    op.create_index('ix_universe_ins_id', 'universe_constituents', ['instrument_id'])
    op.create_index('ix_universe_date', 'universe_constituents', ['date'])
    op.create_index('ix_universe_date_eligible', 'universe_constituents', ['date', 'is_eligible'])

    # Create corporate_events table
    op.create_table(
        'corporate_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('detection_method', sa.String(length=100), nullable=True),
        sa.Column('final_price', sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column('recovery_rate', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.ins_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'event_date', 'event_type', name='uq_events_ins_date_type')
    )
    op.create_index('ix_events_ins_id', 'corporate_events', ['instrument_id'])
    op.create_index('ix_events_date', 'corporate_events', ['event_date'])
    op.create_index('ix_events_type', 'corporate_events', ['event_type'])


def downgrade() -> None:
    op.drop_index('ix_events_type', table_name='corporate_events')
    op.drop_index('ix_events_date', table_name='corporate_events')
    op.drop_index('ix_events_ins_id', table_name='corporate_events')
    op.drop_table('corporate_events')
    op.drop_index('ix_universe_date_eligible', table_name='universe_constituents')
    op.drop_index('ix_universe_date', table_name='universe_constituents')
    op.drop_index('ix_universe_ins_id', table_name='universe_constituents')
    op.drop_table('universe_constituents')
