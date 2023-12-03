"""Create primary key constraints

Revision ID: e8e3ef7a0fd7
Revises: 0b7028b71064
Create Date: 2023-12-03 22:02:39.660770

"""
import sqlalchemy as sa
from alembic import op
from alembic.operations import BatchOperations
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'e8e3ef7a0fd7'
down_revision = '0b7028b71064'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(text("SELECT DISTINCT stashtag_id, emptag_id FROM emp_tags")).all()
    op.execute(text("DELETE FROM emp_tags"))
    # op.execute(emp_tag_map.delete())
    # print(len(conn.execute(text("SELECT DISTINCT stashtag_id, emptag_id FROM emp_tags")).all()))
    for row in rows:
        op.execute(text(f"INSERT INTO emp_tags (stashtag_id, emptag_id) VALUES {row.tuple()}"))
    # conn.commit()

    rows = conn.execute(text("SELECT DISTINCT stashtag, category FROM tag_categories")).all()
    op.execute(text("DELETE FROM tag_categories"))
    # op.execute(list_tags.delete())
    for row in rows:
        op.execute(text(f"INSERT INTO tag_categories (stashtag, category) VALUES {row.tuple()}"))
    # conn.commit()

    with op.batch_alter_table('emp_tags', schema=None) as batch_op:
        batch_op: BatchOperations
        batch_op.alter_column('stashtag_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.alter_column('emptag_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.create_primary_key("pk_emp_tags", ["stashtag_id", "emptag_id"])
        batch_op.drop_constraint('fk_emp_tags_stashtag_id_stash_tag', type_='foreignkey')
        batch_op.drop_constraint('fk_emp_tags_emptag_id_gazelle_tags', type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('fk_emp_tags_emptag_id_gazelle_tags'), 'gazelle_tags', ['emptag_id'],
                                    ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(batch_op.f('fk_emp_tags_stashtag_id_stash_tag'), 'stash_tag', ['stashtag_id'],
                                    ['id'], ondelete='CASCADE')

    with op.batch_alter_table('hf_tags', schema=None) as batch_op:
        batch_op.alter_column('stashtag_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.alter_column('hftag_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.create_primary_key("pk_hf_tags", ["stashtag_id", "hftag_id"])
        batch_op.drop_constraint('fk_hf_tags_hftag_id_gazelle_tags', type_='foreignkey')
        batch_op.drop_constraint('fk_hf_tags_stashtag_id_stash_tag', type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('fk_hf_tags_stashtag_id_stash_tag'), 'stash_tag', ['stashtag_id'],
                                    ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(batch_op.f('fk_hf_tags_hftag_id_gazelle_tags'), 'gazelle_tags', ['hftag_id'],
                                    ['id'], ondelete='CASCADE')

    with op.batch_alter_table('tag_categories', schema=None) as batch_op:
        batch_op.alter_column('stashtag',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.alter_column('category',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.create_primary_key("pk_tag_categories", ["stashtag", "category"])
        batch_op.drop_constraint('fk_tag_categories_stashtag_stash_tag', type_='foreignkey')
        batch_op.drop_constraint('fk_tag_categories_category_category', type_='foreignkey')
        batch_op.create_foreign_key(batch_op.f('fk_tag_categories_category_category'), 'category', ['category'], ['id'],
                                    ondelete='CASCADE')
        batch_op.create_foreign_key(batch_op.f('fk_tag_categories_stashtag_stash_tag'), 'stash_tag', ['stashtag'],
                                    ['id'], ondelete='CASCADE')


def downgrade():
    with op.batch_alter_table('tag_categories', schema=None) as batch_op:
        batch_op: BatchOperations
        batch_op.alter_column('category',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.alter_column('stashtag',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.drop_constraint("pk_tag_categories")
        batch_op.drop_constraint(batch_op.f('fk_tag_categories_stashtag_stash_tag'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_tag_categories_category_category'), type_='foreignkey')
        batch_op.create_foreign_key('fk_tag_categories_category_category', 'category', ['category'], ['id'])
        batch_op.create_foreign_key('fk_tag_categories_stashtag_stash_tag', 'stash_tag', ['stashtag'], ['id'])

    with op.batch_alter_table('hf_tags', schema=None) as batch_op:
        batch_op.alter_column('hftag_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.alter_column('stashtag_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.drop_constraint("pk_hf_tags")
        batch_op.drop_constraint(batch_op.f('fk_hf_tags_hftag_id_gazelle_tags'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_hf_tags_stashtag_id_stash_tag'), type_='foreignkey')
        batch_op.create_foreign_key('fk_hf_tags_stashtag_id_stash_tag', 'stash_tag', ['stashtag_id'], ['id'])
        batch_op.create_foreign_key('fk_hf_tags_hftag_id_gazelle_tags', 'gazelle_tags', ['hftag_id'], ['id'])

    with op.batch_alter_table('emp_tags', schema=None) as batch_op:
        batch_op.alter_column('emptag_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.alter_column('stashtag_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.drop_constraint("pk_emp_tags")
        batch_op.drop_constraint(batch_op.f('fk_emp_tags_stashtag_id_stash_tag'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_emp_tags_emptag_id_gazelle_tags'), type_='foreignkey')
        batch_op.create_foreign_key('fk_emp_tags_emptag_id_gazelle_tags', 'gazelle_tags', ['emptag_id'], ['id'])
        batch_op.create_foreign_key('fk_emp_tags_stashtag_id_stash_tag', 'stash_tag', ['stashtag_id'], ['id'])
