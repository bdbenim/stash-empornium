from typing import Any
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
    "tag_map", Column("stashtag_id", ForeignKey("stash_tag.id")), Column("emptag_id", ForeignKey("emp_tag.id"))
)

list_tags = db.Table(
    "tag_categories",
    Column("stashtag", ForeignKey("stash_tag.id")),
    Column("category", ForeignKey("category.id")),
)


class EmpTag(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tagname: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    stash_tags: Mapped[list["StashTag"]] = db.relationship(secondary=tag_map, back_populates="emp_tags")  # type: ignore


class StashTag(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tagname: Mapped[str] = mapped_column(String(collation="NOCASE"), unique=True, nullable=False)
    display: Mapped[str] = mapped_column(String, nullable=True)
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emp_tags: Mapped[list[EmpTag]] = db.relationship("EmpTag", secondary=tag_map, back_populates="stash_tags")  # type: ignore
    categories: Mapped[list["Category"]] = db.relationship("Category", secondary=list_tags, back_populates="tags")  # type: ignore


class Category(db.Model):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    tags: Mapped[list[StashTag]] = db.relationship(secondary=list_tags, back_populates="categories")  # type: ignore


def get_or_create(model: type, **kwargs):
    session = db.session
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    else:
        instance = model(**kwargs)
        session.add(instance)
        session.commit()
        return instance


def get_or_create_no_commit(model: type, **kwargs):
    session = db.session
    instance = session.query(model).filter_by(**kwargs).first()
    if instance:
        return instance
    else:
        instance = model(**kwargs)
        session.add(instance)
        return instance


def to_dict() -> dict[str, Any]:
    categories = Category.query.all()
    s_tags = StashTag.query.all()
    e_tags = EmpTag.query.all()
    data = {"stash_tags": [], "emp_tags": [], "categories": []}
    for tag in s_tags:
        assert isinstance(tag, StashTag)
        stag = {
            "id": tag.id,
            "name": tag.tagname,
            "display": tag.display,
            "ignored": tag.ignored,
            "emp_tags": [e.id for e in tag.emp_tags],
            "categories": [c.id for c in tag.categories],
        }
        data["stash_tags"].append(stag)

    for cat in categories:
        assert isinstance(cat, Category)
        category = {"id": cat.id, "name": cat.name}
        data["categories"].append(category)

    for tag in e_tags:
        assert isinstance(tag, EmpTag)
        etag = {"id": tag.id, "name": tag.tagname}
        data["emp_tags"].append(etag)

    return data


def from_dict(data: dict[str, Any]) -> None:
    # 1. Delete existing records
    Category.query.delete()
    StashTag.query.delete()
    EmpTag.query.delete()

    # 2. Categories
    for cat in data["categories"]:
        db.session.add(Category(id=cat["id"], name=cat["name"]))  # type: ignore
    db.session.commit()

    # 3. EMP Tags
    for tag in data["emp_tags"]:
        db.session.add(EmpTag(id=tag["id"], tagname=tag["name"]))  # type: ignore
    db.session.commit()

    # 4. Stash Tags
    for tag in data["stash_tags"]:
        stag = StashTag(
            id=tag["id"], tagname=tag["name"], ignored=tag["ignored"], display=tag["display"]
        )  # type: ignore
        db.session.add(stag)
        for id in tag["categories"]:
            cat = Category.query.filter_by(id=id).first()
            assert cat is not None
            stag.categories.append(cat)
        for id in tag["emp_tags"]:
            etag = EmpTag.query.filter_by(id=id).first()
            assert etag is not None
            stag.emp_tags.append(etag)
    db.session.commit()
