"""phone app alerts

Revision ID: 7c41d2e9a0f3
Revises: 35296a515abb
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.models.base


revision: str = '7c41d2e9a0f3'
down_revision: str | None = '35296a515abb'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'push_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=512), nullable=False),
        sa.Column('created_at', app.models.base.UTCDateTime(), nullable=False),
        sa.Column('last_seen_at', app.models.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token', name='uq_push_device_token'),
    )
    op.create_index(op.f('ix_push_devices_user_id'), 'push_devices', ['user_id'], unique=False)
    with op.batch_alter_table('alert_deliveries') as batch_op:
        batch_op.add_column(sa.Column('push_cancelled_at', app.models.base.UTCDateTime(), nullable=True))
    with op.batch_alter_table('staff_members') as batch_op:
        # Existing staff get alerts as soon as they install the app and sign in.
        batch_op.add_column(sa.Column('notify_push', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table('staff_members') as batch_op:
        batch_op.drop_column('notify_push')
    with op.batch_alter_table('alert_deliveries') as batch_op:
        batch_op.drop_column('push_cancelled_at')
    op.drop_index(op.f('ix_push_devices_user_id'), table_name='push_devices')
    op.drop_table('push_devices')
