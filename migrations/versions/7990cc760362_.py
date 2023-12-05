"""Initial database creation

Revision ID: 7990cc760362
Revises: 
Create Date: 2023-12-02 19:10:05.966030

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7990cc760362'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('category',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('name', sa.String(), nullable=False),
                    sa.PrimaryKeyConstraint('id', name=op.f('pk_category')),
                    sa.UniqueConstraint('name', name=op.f('uq_category_name'))
                    )
    op.create_table('emp_tag',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('tagname', sa.String(length=32), nullable=False),
                    sa.PrimaryKeyConstraint('id', name=op.f('pk_emp_tag')),
                    sa.UniqueConstraint('tagname', name=op.f('uq_emp_tag_tagname'))
                    )
    op.create_table('stash_tag',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('tagname', sa.String(collation='NOCASE'), nullable=False),
                    sa.Column('display', sa.String(), nullable=True),
                    sa.Column('ignored', sa.Boolean(), nullable=False),
                    sa.PrimaryKeyConstraint('id', name=op.f('pk_stash_tag')),
                    sa.UniqueConstraint('tagname', name=op.f('uq_stash_tag_tagname'))
                    )
    op.create_table('tag_categories',
                    sa.Column('stashtag', sa.Integer(), nullable=True),
                    sa.Column('category', sa.Integer(), nullable=True),
                    sa.ForeignKeyConstraint(['category'], ['category.id'],
                                            name=op.f('fk_tag_categories_category_category')),
                    sa.ForeignKeyConstraint(['stashtag'], ['stash_tag.id'],
                                            name=op.f('fk_tag_categories_stashtag_stash_tag'))
                    )
    op.create_table('tag_map',
                    sa.Column('stashtag_id', sa.Integer(), nullable=True),
                    sa.Column('emptag_id', sa.Integer(), nullable=True),
                    sa.ForeignKeyConstraint(['emptag_id'], ['emp_tag.id'], name=op.f('fk_tag_map_emptag_id_emp_tag')),
                    sa.ForeignKeyConstraint(['stashtag_id'], ['stash_tag.id'],
                                            name=op.f('fk_tag_map_stashtag_id_stash_tag'))
                    )


def downgrade() -> None:
    op.drop_table('tag_map')
    op.drop_table('tag_categories')
    op.drop_table('stash_tag')
    op.drop_table('emp_tag')
    op.drop_table('category')
