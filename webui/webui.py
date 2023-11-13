from flask import Blueprint, abort, redirect, render_template, url_for, request
from webui.forms import (
    TagMapForm,
    BackendSettings,
    RedisSettings,
    RTorrentSettings,
    DelugeSettings,
    QBittorrentSettings,
    StashSettings,
    TagAdvancedForm,
    CategoryList,
    SearchForm
)

from utils.confighandler import ConfigHandler
from utils.taghandler import TagHandler
from utils.db import get_or_create, StashTag, EmpTag, db, get_or_create_no_commit, Category
from werkzeug.exceptions import HTTPException

conf = ConfigHandler()

settings_page = Blueprint("settings_page", __name__, template_folder="templates")


@settings_page.route("/", methods=["GET"])
def index():
    return redirect(url_for(".settings", page="backend"))


@settings_page.route("/tags")
def tags():
    return redirect(url_for(".tag_settings", page="maps"))


@settings_page.route("/tag/<id>", methods=["GET", "POST"])
def tag(id):
    tag: StashTag = StashTag.query.filter_by(id=id).first_or_404()
    form = TagAdvancedForm(tag=tag)
    if form.validate_on_submit():
        print(form.data)
        if form.data["save"]:
            tag.ignored = form.data["ignored"]
            tag.emp_tags.clear()
            for et in form.data["emp_tags"].split():
                e_tag = get_or_create_no_commit(EmpTag, tagname=et)
                tag.emp_tags.append(e_tag)
            tag.categories.clear()
            for cat in form.data["categories"]:
                category = get_or_create_no_commit(Category, name=cat)
                tag.categories.append(category)
            db.session.commit()
        elif form.data["delete"]:
            db.session.delete(tag)
            db.session.commit()
    return render_template("tag-advanced.html", form=form)


@settings_page.route("/tags/<page>", methods=["GET", "POST"])
def tag_settings(page):
    pagination = TagHandler().queryMaps(page=int(page))
    form = TagMapForm(s_tags=pagination.items)
    if form.validate_on_submit():
        tag = form.update_self()
        if tag:
            s_tag = get_or_create(StashTag, tagname=tag["stash_tag"])
            db.session.delete(s_tag)
            db.session.commit()
        if form.data["submit"]:
            for tag in form.data["tags"]:
                if not tag["stash_tag"]:
                    continue  # Ignore empty tag inputs
                s_tag = get_or_create(StashTag, tagname=tag["stash_tag"])
                e_tags = []
                for et in tag["emp_tag"].split():
                    e_tags.append(get_or_create(EmpTag, tagname=et))
                s_tag.emp_tags = e_tags
                db.session.commit()
        else:
            for tag in form.data["tags"]:
                if tag["advanced"]:
                    stag = StashTag.query.filter_by(tagname=tag["stash_tag"]).first_or_404()
                    return redirect(url_for(".tag", id=stag.id))
    return render_template("tag-settings.html", form=form, pagination=pagination)



@settings_page.route("/search", methods=['GET', 'POST'])
def search():
    tags = StashTag.query
    page = request.args.get("page", default=1, type=int)
    searched = request.args.get("search")
    form = SearchForm()
    if form.validate_on_submit():
        for tag in form.tags:
            s_tag = StashTag.query.filter_by(tagname=tag.stash_tag.data).first_or_404()
            if tag.settings.data:
                return redirect(url_for(".tag", id=s_tag.id))
    elif searched:
        # searched = form.search.data
        tags = tags.filter(StashTag.tagname.like(f"%{searched}%"))
        pagination = tags.order_by(StashTag.tagname).paginate(page=page)
        form = SearchForm(s_tags=pagination.items)
        return render_template("search.html", searched=searched, form=form, pagination=pagination)
    return render_template("search.html")

@settings_page.route("/categories")
def category():
    return redirect(url_for(".category_settings", page=1))

@settings_page.route("/categories/<page>", methods=["GET", "POST"])
def category_settings(page):
    pagination = Category.query.paginate(page=int(page))
    form = CategoryList(category_objs=pagination.items)
    if form.validate_on_submit():
        cat = form.update_self()
        if cat:
            cat = Category.query.filter_by(name=cat).first()
            db.session.delete(cat)
            db.session.commit()
        elif form.submit.data:
            for cat in form.categories.data:
                cat = get_or_create(Category, name=cat["name"])
    return render_template("categories.html", form=form, pagination=pagination)

@settings_page.route("/settings/<page>", methods=["GET", "POST"])
def settings(page):
    template_context = {}
    enable = page in conf and not conf.get(page, "disable", False)
    match page:
        case "backend":
            template_context["settings_option"] = "your stash-empornium backend"
            form = BackendSettings(
                default_template=conf.get(page, "default_template", ""),
                torrent_directories=", ".join(conf.get(page, "torrent_directories", "")),  # type: ignore
                port=conf.get(page, "port", ""),
                date_format=conf.get(page, "date_format", ""),
                title_template=conf.get(page, "title_template", ""),
                media_directory=conf.get(page, "media_directory", ""),
                move_method=conf.get(page, "move_method", "copy"),
                anon=conf.get(page, "anon", False),
                choices=[opt for opt in conf["templates"]],  # type: ignore
            )
        case "stash":
            template_context["settings_option"] = "your stash server"
            form = StashSettings(url=conf.get(page, "url", ""), api_key=conf.get(page, "api_key", ""))
        case "redis":
            template_context["settings_option"] = "your redis server"
            form = RedisSettings(
                enable_form=enable,
                host=conf.get(page, "host", ""),
                port=conf.get(page, "port", ""),
                username=conf.get(page, "username", ""),
                password=conf.get(page, "password", ""),
                ssl=conf.get(page, "ssl", False),
            )
        case "rtorrent":
            template_context["settings_option"] = "your rTorrent client"
            form = RTorrentSettings(
                enable_form=enable,
                host=conf.get(page, "host", ""),
                port=conf.get(page, "port", ""),
                username=conf.get(page, "username", ""),
                password=conf.get(page, "password", ""),
                path=conf.get(page, "path", "RPC2"),
                label=conf.get(page, "label", ""),
                ssl=conf.get(page, "ssl", False),
            )
        case "deluge":
            template_context["settings_option"] = "your Deluge client"
            form = DelugeSettings(
                enable_form=enable,
                host=conf.get(page, "host", ""),
                port=conf.get(page, "port", ""),
                password=conf.get(page, "password", ""),
                ssl=conf.get(page, "ssl", False),
            )
        case "qbittorrent":
            template_context["settings_option"] = "your qBittorrent client"
            form = QBittorrentSettings(
                enable_form=enable,
                host=conf.get(page, "host", ""),
                port=conf.get(page, "port", ""),
                username=conf.get(page, "username", ""),
                password=conf.get(page, "password", ""),
                label=conf.get(page, "label", ""),
                ssl=conf.get(page, "ssl", False),
            )
        case "tags":
            return redirect(url_for(".tag_settings", page="maps"))
        case _:
            abort(404)
    if form.validate_on_submit():
        template_context["message"] = "Settings saved"
        match page:
            case "backend":
                conf.set(page, "default_template", form.data["default_template"])
                conf.set(page, "torrent_directories", [x.strip() for x in form.data["torrent_directories"].split(",")])
                conf.set(page, "port", int(form.data["port"]))
                conf.set(page, "title_template", form.data["title_template"])
                conf.set(page, "date_format", form.data["date_format"])
                if form.data["media_directory"]:
                    conf.set(page, "media_directory", form.data["media_directory"])
                conf.set(page, "move_method", form.data["move_method"])
                conf.set(page, "anon", form.data["anon"])
            case "stash":
                conf.set(page, "url", form.data["url"])
                if form.data["api_key"]:
                    conf.set(page, "api_key", form.data["api_key"])
                else:
                    conf.delete(page, "api_key")
            case "redis":
                if form.data["enable_form"]:
                    conf.set(page, "disable", False)
                    conf.set(page, "host", form.data["host"])
                    conf.set(page, "port", int(form.data["port"]))
                    conf.set(page, "ssl", form.data["ssl"])
                    if form.data["username"]:
                        conf.set(page, "username", form.data["username"])
                    else:
                        conf.delete(page, "username")
                    if form.data["password"]:
                        conf.set(page, "password", form.data["password"])
                    else:
                        conf.delete(page, "password")
                else:
                    if page in conf:
                        conf.set(page, "disable", True)
            case "rtorrent":
                if form.data["enable_form"]:
                    conf.set(page, "disable", False)
                    conf.set(page, "host", form.data["host"])
                    conf.set(page, "port", int(form.data["port"]))
                    conf.set(page, "ssl", form.data["ssl"])
                    conf.set(page, "path", form.data["path"])
                    if form.data["username"]:
                        conf.set(page, "username", form.data["username"])
                    else:
                        conf.delete(page, "username")
                    if form.data["password"]:
                        conf.set(page, "password", form.data["password"])
                    else:
                        conf.delete(page, "password")
                    if form.data["label"]:
                        conf.set(page, "label", form.data["label"])
                    else:
                        conf.delete(page, "label")
                else:
                    if page in conf:
                        conf.set(page, "disable", True)
                conf.configureTorrents()
            case "deluge":
                if form.data["enable_form"]:
                    conf.set(page, "disable", False)
                    conf.set(page, "host", form.data["host"])
                    conf.set(page, "port", int(form.data["port"]))
                    conf.set(page, "ssl", form.data["ssl"])
                    if form.data["password"]:
                        conf.set(page, "password", form.data["password"])
                    else:
                        conf.delete(page, "password")
                else:
                    if page in conf:
                        conf.set(page, "disable", True)
                conf.configureTorrents()
            case "qbittorrent":
                if form.data["enable_form"]:
                    conf.set(page, "disable", False)
                    conf.set(page, "host", form.data["host"])
                    conf.set(page, "port", int(form.data["port"]))
                    conf.set(page, "ssl", form.data["ssl"])
                    if form.data["username"]:
                        conf.set(page, "username", form.data["username"])
                    else:
                        conf.delete(page, "username")
                    if form.data["password"]:
                        conf.set(page, "password", form.data["password"])
                    else:
                        conf.delete(page, "password")
                    if form.data["label"]:
                        conf.set(page, "label", form.data["label"])
                    else:
                        conf.delete(page, "label")
                else:
                    if page in conf:
                        conf.set(page, "disable", True)
                conf.configureTorrents()
            case _:
                abort(404)
        conf.update_file()
    template_context["form"] = form
    return render_template("settings.html", **template_context)

@settings_page.app_errorhandler(HTTPException)
def handle_exception(e):
    message = e.name
    if e.code == 404:
        message = "The page you were looking for was not found"
    return render_template("errorpage.html", code=e.code, message=message)
