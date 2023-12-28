"""Add global default tag maps

Revision ID: feb7b60bf53f
Revises: 017767fd9fdb
Create Date: 2023-12-27 10:17:24.231424

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'feb7b60bf53f'
down_revision = '017767fd9fdb'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('def_tags',
                    sa.Column('stashtag_id', sa.Integer(), nullable=False),
                    sa.Column('gazelletag_id', sa.Integer(), nullable=False),
                    sa.ForeignKeyConstraint(['gazelletag_id'], ['gazelle_tags.id'],
                                            name=op.f('fk_def_tags_gazelletag_id_gazelle_tags'), ondelete='CASCADE'),
                    sa.ForeignKeyConstraint(['stashtag_id'], ['stash_tag.id'],
                                            name=op.f('fk_def_tags_stashtag_id_stash_tag'), ondelete='CASCADE'),
                    sa.PrimaryKeyConstraint('stashtag_id', 'gazelletag_id', name=op.f('pk_def_tags'))
                    )
    op.execute(sa.text("INSERT INTO def_tags (stashtag_id, gazelletag_id) SELECT stashtag_id, emptag_id FROM emp_tags"))


def downgrade():
    op.drop_table('def_tags')
