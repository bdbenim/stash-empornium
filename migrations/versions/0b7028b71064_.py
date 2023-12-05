"""Add HF tags

Revision ID: 0b7028b71064
Revises: 7990cc760362
Create Date: 2023-12-02 21:13:11.813492

"""
import sqlalchemy as sa
from alembic import op
from alembic.operations.ops import CreatePrimaryKeyOp
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '0b7028b71064'
down_revision = '7990cc760362'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    ctx = op.get_context()
    existing_metadata = sa.schema.MetaData()
    target_metadata = ctx.opts['target_metadata']

    op.execute(text("pragma foreign_keys=OFF"))

    # Rename tables.
    op.rename_table("emp_tag", "gazelle_tags")
    op.rename_table("tag_map", "emp_tags")

    # Drop PK and FKs reflected from existing table.
    existing_table = sa.Table("gazelle_tags", existing_metadata, autoload_with=conn)
    with op.batch_alter_table("gazelle_tags") as batch_op:
        batch_op.drop_constraint(existing_table.primary_key.name)

        # Recreate PK and FKs according to naming convention and current class name.
        target_table = sa.Table("gazelle_tags", target_metadata)
        batch_op.invoke(CreatePrimaryKeyOp.from_constraint(target_table.primary_key))
        batch_op.drop_constraint("uq_emp_tag_tagname")
        batch_op.create_unique_constraint(op.f("uq_gazelle_tags_tagname"), ["tagname"])

    # Drop PK and FKs reflected from existing table.
    existing_table = sa.Table("emp_tags", existing_metadata, autoload_with=conn)
    with op.batch_alter_table("emp_tags") as batch_op:
        for c in existing_table.foreign_key_constraints:
            batch_op.drop_constraint(c.name)

        # Recreate PK and FKs according to naming convention and current class name.
        batch_op.create_foreign_key(op.f('fk_emp_tags_emptag_id_gazelle_tags'), "gazelle_tags", ["emptag_id"], ["id"])
        batch_op.create_foreign_key(op.f('fk_emp_tags_stashtag_id_stash_tag'), "stash_tag", ["stashtag_id"], ["id"])

    op.create_table('hf_tags', sa.Column('stashtag_id', sa.Integer(), nullable=True),
                    sa.Column('hftag_id', sa.Integer(), nullable=True),
                    sa.ForeignKeyConstraint(['hftag_id'], ['gazelle_tags.id'], ),
                    sa.ForeignKeyConstraint(['stashtag_id'], ['stash_tag.id']))

    op.execute(text("pragma foreign_keys=ON"))


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('hf_tags')  # ### end Alembic commands ###
    op.rename_table("gazelle_tags", "emp_tag")
    op.rename_table("emp_tags", "tag_map")
