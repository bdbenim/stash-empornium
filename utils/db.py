import logging
from typing import Any

import sqlalchemy.exc
from flask_migrate import upgrade as fm_upgrade
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, String, Integer, ForeignKey, Column, Boolean, text
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped

__schema__ = 2


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


def upgrade():
    logger = logging.getLogger(__name__)
    base_rev = '7990cc760362'
    t = text(f"INSERT INTO alembic_version VALUES('{base_rev}')")
    with db.engine.connect() as con:
        with con.begin():
            # con.execute(text("PRAGMA foreign_keys = ON"))  # sqlite ignores foreign keys otherwise
            try:
                stmt = text("SELECT version_num FROM alembic_version")
                result = con.execute(stmt).first()[0]
                logger.debug(f"DB revision: {result}")
            except TypeError:
                con.execute(t)
            except sqlalchemy.exc.OperationalError:
                try:
                    con.execute(text("SELECT COUNT(*) FROM stash_tag")).first()  # Confirm that DB is not empty
                    logger.debug("Initializing alembic_version table")
                    con.execute(text("""CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL, 
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
        )"""))
                    con.execute(t)
                except sqlalchemy.exc.OperationalError:
                    pass  # DB was empty, so allow Alembic to create
        fm_upgrade()
        con.execute(text("VACUUM"))
        con.commit()


# alembic_version = db.Table("alembic_version", Column(name="version_num", type_=String(32)))

emp_tag_map = db.Table(
    "emp_tags",
    Column("stashtag_id",
           ForeignKey("stash_tag.id", ondelete="CASCADE"), primary_key=True),
    Column("emptag_id",
           ForeignKey("gazelle_tags.id", ondelete="CASCADE"), primary_key=True)
)

hf_tag_map = db.Table(
    "hf_tags",
    Column("stashtag_id",
           ForeignKey("stash_tag.id", ondelete="CASCADE"), primary_key=True),
    Column("hftag_id",
           ForeignKey("gazelle_tags.id", ondelete="CASCADE"), primary_key=True)
)

fc_tag_map = db.Table(
    "fc_tags",
    Column("stashtag_id",
           ForeignKey("stash_tag.id", ondelete="CASCADE"), primary_key=True),
    Column("fctag_id",
           ForeignKey("gazelle_tags.id", ondelete="CASCADE"), primary_key=True)
)

pb_tag_map = db.Table(
    "pb_tags",
    Column("stashtag_id",
           ForeignKey("stash_tag.id", ondelete="CASCADE"), primary_key=True),
    Column("pbtag_id",
           ForeignKey("gazelle_tags.id", ondelete="CASCADE"), primary_key=True)
)

ent_tag_map = db.Table(
    "ent_tags",
    Column("stashtag_id",
           ForeignKey("stash_tag.id", ondelete="CASCADE"), primary_key=True),
    Column("enttag_id",
           ForeignKey("gazelle_tags.id", ondelete="CASCADE"), primary_key=True)
)

list_tags = db.Table(
    "tag_categories",
    Column("stashtag", ForeignKey("stash_tag.id", ondelete="CASCADE"), primary_key=True),
    Column("category", ForeignKey("category.id", ondelete="CASCADE"), primary_key=True),
)


class GazelleTag(db.Model):
    __tablename__ = "gazelle_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tagname: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    emp_stash_tags: Mapped[list["StashTag"]] = db.relationship(secondary=emp_tag_map,
                                                               back_populates="emp_tags",
                                                               passive_deletes=True)  # type: ignore
    hf_stash_tags: Mapped[list["StashTag"]] = db.relationship(secondary=hf_tag_map,
                                                              back_populates="hf_tags",
                                                              passive_deletes=True)  # type: ignore
    fc_stash_tags: Mapped[list["StashTag"]] = db.relationship(secondary=fc_tag_map,
                                                              back_populates="fc_tags",
                                                              passive_deletes=True)  # type: ignore
    pb_stash_tags: Mapped[list["StashTag"]] = db.relationship(secondary=pb_tag_map,
                                                              back_populates="pb_tags",
                                                              passive_deletes=True)  # type: ignore
    ent_stash_tags: Mapped[list["StashTag"]] = db.relationship(secondary=ent_tag_map,
                                                               back_populates="ent_tags",
                                                               passive_deletes=True)  # type: ignore


class StashTag(db.Model):
    __tablename__ = "stash_tag"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tagname: Mapped[str] = mapped_column(String(collation="NOCASE"), unique=True, nullable=False)
    display: Mapped[str] = mapped_column(String, nullable=True)
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    emp_tags: Mapped[list[GazelleTag]] = db.relationship("GazelleTag", secondary=emp_tag_map,
                                                         back_populates="emp_stash_tags",
                                                         passive_deletes=True)  # type: ignore
    hf_tags: Mapped[list[GazelleTag]] = db.relationship("GazelleTag", secondary=hf_tag_map,
                                                        back_populates="hf_stash_tags",
                                                        passive_deletes=True)  # type: ignore
    fc_tags: Mapped[list[GazelleTag]] = db.relationship("GazelleTag", secondary=fc_tag_map,
                                                        back_populates="fc_stash_tags",
                                                        passive_deletes=True)  # type: ignore
    pb_tags: Mapped[list[GazelleTag]] = db.relationship("GazelleTag", secondary=pb_tag_map,
                                                        back_populates="pb_stash_tags",
                                                        passive_deletes=True)  # type: ignore
    ent_tags: Mapped[list[GazelleTag]] = db.relationship("GazelleTag", secondary=ent_tag_map,
                                                         back_populates="ent_stash_tags",
                                                         passive_deletes=True)  # type: ignore
    categories: Mapped[list["Category"]] = db.relationship("Category", secondary=list_tags,
                                                           back_populates="tags",
                                                           passive_deletes=True)  # type: ignore


class Category(db.Model):
    __tablename__ = "category"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    tags: Mapped[list[StashTag]] = db.relationship(secondary=list_tags, back_populates="categories",
                                                   passive_deletes=True)  # type: ignore


def get_or_create[T](model: type[T], **kwargs) -> T:
    session = db.session
    with session.no_autoflush:
        instance = session.query(model).filter_by(**kwargs).first()
        if instance:
            return instance
        else:
            instance = model(**kwargs)
            session.add(instance)
            session.commit()
            return instance


def get_or_create_no_commit[T](model: type[T], **kwargs) -> T:
    session = db.session
    with session.no_autoflush:
        instance = session.query(model).filter_by(**kwargs).first()
        if instance:
            return instance
        else:
            instance = model(**kwargs)
            session.add(instance)
            # session.flush()
            return instance


def to_dict() -> dict[str, Any]:
    categories: list[Category] = Category.query.all()
    s_tags: list[StashTag] = StashTag.query.all()
    g_tags: list[GazelleTag] = GazelleTag.query.all()
    data = {"revision": "", "stash_tags": [], "gazelle_tags": [], "categories": []}
    for tag in s_tags:
        stag = {
            "id": tag.id,
            "name": tag.tagname,
            "display": tag.display,
            "ignored": tag.ignored,
            "emp_tags": [e.id for e in tag.emp_tags],
            "hf_tags": [h.id for h in tag.hf_tags],
            "fc_tags": [h.id for h in tag.fc_tags],
            "pb_tags": [h.id for h in tag.pb_tags],
            "ent_tags": [h.id for h in tag.ent_tags],
            "categories": [c.id for c in tag.categories],
        }
        data["stash_tags"].append(stag)

    for cat in categories:
        category = {"id": cat.id, "name": cat.name}
        data["categories"].append(category)

    for tag in g_tags:
        etag = {"id": tag.id, "name": tag.tagname}
        data["gazelle_tags"].append(etag)

    rev = db.session.execute(text("SELECT version_num FROM alembic_version")).first()[0]
    data['revision'] = rev

    return data


def from_dict(data: dict[str, Any]) -> None:
    rev = db.session.execute(text("SELECT version_num FROM alembic_version")).first()[0]
    if data["revision"] != rev:
        raise ValueError("Schema version mismatch")

    with db.session.begin():
        # 1. Delete existing records
        Category.query.delete()
        StashTag.query.delete()
        GazelleTag.query.delete()

        # 2. Categories
        for cat in data["categories"]:
            db.session.add(Category(id=cat["id"], name=cat["name"]))  # type: ignore
        db.session.flush()

        # 3. EMP Tags
        for tag in data["gazelle_tags"]:
            db.session.add(GazelleTag(id=tag["id"], tagname=tag["name"]))  # type: ignore
        db.session.flush()

        # 4. Stash Tags
        for tag in data["stash_tags"]:
            stag = StashTag(
                id=tag["id"], tagname=tag["name"], ignored=tag["ignored"], display=tag["display"]
            )  # type: ignore
            db.session.add(stag)
            for tag_id in tag["categories"]:
                cat = Category.query.filter_by(id=tag_id).first()
                assert cat is not None
                stag.categories.append(cat)
            for tag_id in tag["emp_tags"]:
                etag = GazelleTag.query.filter_by(id=tag_id).first()
                assert etag is not None
                stag.emp_tags.append(etag)
            for tag_id in tag["hf_tags"]:
                etag = GazelleTag.query.filter_by(id=tag_id).first()
                assert etag is not None
                stag.hf_tags.append(etag)
            for tag_id in tag["fc_tags"]:
                etag = GazelleTag.query.filter_by(id=tag_id).first()
                assert etag is not None
                stag.fc_tags.append(etag)
            for tag_id in tag["pb_tags"]:
                etag = GazelleTag.query.filter_by(id=tag_id).first()
                assert etag is not None
                stag.pb_tags.append(etag)
            for tag_id in tag["ent_tags"]:
                etag = GazelleTag.query.filter_by(id=tag_id).first()
                assert etag is not None
                stag.ent_tags.append(etag)
