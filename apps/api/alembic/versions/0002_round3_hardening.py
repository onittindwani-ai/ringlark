"""one time call actions, consent notes, indexes on the vendor call ids

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
import sendora_core.db


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('rm_call_action',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('call_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('created_at', sendora_core.db.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['call_id'], ['rm_call.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('call_id', 'kind')
    )
    with op.batch_alter_table('rm_consent', schema=None) as batch_op:
        batch_op.add_column(sa.Column('note', sa.String(length=300), server_default='', nullable=False))
    with op.batch_alter_table('rm_call', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rm_call_external_id'), ['external_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rm_call_telnyx_call_id'), ['telnyx_call_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('rm_call', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rm_call_telnyx_call_id'))
        batch_op.drop_index(batch_op.f('ix_rm_call_external_id'))
    with op.batch_alter_table('rm_consent', schema=None) as batch_op:
        batch_op.drop_column('note')
    op.drop_table('rm_call_action')
