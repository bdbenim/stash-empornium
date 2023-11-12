from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy import MetaData, String, Integer, ForeignKey, Column, Boolean


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


db = SQLAlchemy(model_class=Base)

tag_map = db.Table(
    "tag_map",
    Column("stashtag_id", ForeignKey("stash_tag.id")),
    Column("emptag_id", ForeignKey("emp_tag.id"))
)

list_tags = db.Table(
    "tag_categories",
    Column("stashtag", ForeignKey("stash_tag.id")),
    Column("category", ForeignKey("category.id")),
)

class EmpTag(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tagname: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)


class StashTag(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tagname: Mapped[str] = mapped_column(String(collation='NOCASE'), unique=True, nullable=False)
    display: Mapped[str] = mapped_column(String, nullable=True)
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emp_tags: Mapped[list[EmpTag]] = db.relationship("EmpTag", secondary=tag_map) # type: ignore
    categories: Mapped[list["Category"]] = db.relationship("Category", secondary=list_tags) # type: ignore

class Category(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)


def get_or_create(model, **kwargs):
    session = db.session
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    else:
        instance = model(**kwargs)
        session.add(instance)
        session.commit()
        return instance