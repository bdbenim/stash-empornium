import json
import tempfile
from flask import Blueprint, abort, redirect, render_template, url_for, request, send_file, render_template_string
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
    SearchForm,
    FileMapForm,
    TorrentSettings,
    DBImportExport, HamsterForm, ImageSettings
)

from utils.confighandler import ConfigHandler
from utils.taghandler import query_maps
from utils.db import get_or_create, StashTag, GazelleTag, db, get_or_create_no_commit, Category, from_dict, to_dict
from werkzeug.exceptions import HTTPException

DUMMY_CONTEXT = {
    "title": "Big Buck Bunny",
    "date": "2008-05-20",
    "studio": "Blender Foundation",
    "performers": ["Big Buck Bunny", "Frank", "Rinky", "Gimera"],
    "resolution": "1080p",
    "codec": "h264",
    "duration": "10:00",
    "framerate": "24"
}

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
    stag: StashTag = StashTag.query.filter_by(id=id).first_or_404()
    form = TagAdvancedForm(tag=stag)
    if form.validate_on_submit():
        if form.data["save"]:
            stag.ignored = form.data["ignored"]
            stag.display = form.data["display"]
            etags = []
            for et in form.data["def_tags"].split():
                etags.append(get_or_create_no_commit(GazelleTag, tagname=et))
            stag.def_tags = etags
            etags = []
            for et in form.data["emp_tags"].split():
                etags.append(get_or_create_no_commit(GazelleTag, tagname=et))
            stag.emp_tags = etags
            etags = []
            for et in form.data["pb_tags"].split():
                etags.append(get_or_create_no_commit(GazelleTag, tagname=et))
            stag.pb_tags = etags
            etags = []
            for et in form.data["fc_tags"].split():
                etags.append(get_or_create_no_commit(GazelleTag, tagname=et))
            stag.fc_tags = etags
            etags = []
            for et in form.data["ent_tags"].split():
                etags.append(get_or_create_no_commit(GazelleTag, tagname=et))
            stag.ent_tags = etags
            etags = []
            for et in form.data["hf_tags"].split():
                etags.append(get_or_create_no_commit(GazelleTag, tagname=et))
            stag.hf_tags = etags
            cats = []
            for cat in form.data["categories"]:
                cats.append(get_or_create_no_commit(Category, name=cat))
            stag.categories = cats
            db.session.commit()
        elif form.data["delete"]:
            db.session.delete(stag)
            db.session.commit()
    return render_template("tag-advanced.html", form=form)


@settings_page.route("/tags/<page>", methods=["GET", "POST"])
def tag_settings(page):
    pagination = query_maps(page=int(page))
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
                    e_tags.append(get_or_create(GazelleTag, tagname=et))
                s_tag.emp_tags = e_tags
                db.session.commit()
        else:
            for tag in form.data["tags"]:
                if tag["advanced"]:
                    stag = StashTag.query.filter_by(tagname=tag["stash_tag"]).first_or_404()
                    return redirect(url_for(".tag", id=stag.id))
    return render_template("tag-settings.html", form=form, pagination=pagination)


@settings_page.route("/search", methods=["GET", "POST"])
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
        tags = tags.filter(StashTag.tagname.like(f"%{searched}%"))
        e_tags = StashTag.query.join(StashTag.emp_tags).filter(GazelleTag.tagname.like(f"%{searched}%"))
        tags = tags.union(e_tags)
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
    template = "settings.html"
    enable = page in conf and not conf.get(page, "disable", False)
    match page:
        case "backend":
            template_context["settings_option"] = "your stash-empornium backend"
            title_template = conf.get(page, "title_template", "")
            form = BackendSettings(
                default_template=conf.get(page, "default_template", ""),
                torrent_directories=", ".join(conf.get(page, "torrent_directories", "")),  # type: ignore
                port=conf.get(page, "port", ""),
                date_format=conf.get(page, "date_format", ""),
                title_template=title_template,
                title_example = render_template_string(title_template, **DUMMY_CONTEXT),
                media_directory=conf.get(page, "media_directory", ""),
                move_method=conf.get(page, "move_method", "copy"),
                anon=conf.get(page, "anon", False),
                choices=[opt for opt in conf["templates"]],  # type: ignore
                tag_codec = conf.get("metadata", "tag_codec", False),
                tag_date = conf.get("metadata", "tag_date", False),
                tag_framerate = conf.get("metadata", "tag_framerate", False),
                tag_resolution = conf.get("metadata", "tag_resolution", False),
            )
        case "images":
            template_context["settings_option"] = "your images"
            form = ImageSettings(
                upload_gif=conf.get(page, "use_preview", False),
                use_gif=conf.get(page, "animated_cover", False),
                contact_sheet_layout=conf.get(page, "contact_sheet_layout", ""),
                num_screens=conf.get(page, "num_screens", 10),
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
                maps=conf.get(page, "pathmaps", {})
            )
        case "deluge":
            template_context["settings_option"] = "your Deluge client"
            form = DelugeSettings(
                enable_form=enable,
                host=conf.get(page, "host", ""),
                port=conf.get(page, "port", ""),
                password=conf.get(page, "password", ""),
                ssl=conf.get(page, "ssl", False),
                maps=conf.get(page, "pathmaps", {})
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
                maps=conf.get(page, "pathmaps", {})
            )
        case "transmission":
            template_context["settings_option"] = "your Transmission client"
            form = RTorrentSettings(
                enable_form=enable,
                host=conf.get(page, "host", ""),
                port=conf.get(page, "port", ""),
                username=conf.get(page, "username", ""),
                password=conf.get(page, "password", ""),
                path=conf.get(page, "path", "/transmission/rpc"),
                label=conf.get(page, "label", ""),
                ssl=conf.get(page, "ssl", False),
                maps=conf.get(page, "pathmaps", {})
            )
        case "files":
            template_context["settings_option"] = "stash path mappings"
            form = FileMapForm(maps=conf.get("stash", "maps"))
            for field in form.file_maps.entries:
                field["remote_path"].render_kw = {
                    "data-toggle": "tooltip",
                    "title": "This is the path as stash sees it",
                }
        case "hamster":
            template_context["settings_option"] = "your hamster account"
            form = HamsterForm(api_key=conf.get(page, "api_key", ""))
        case "tags":
            return redirect(url_for(".tag_settings", page="maps"))
        case "database":
            template_context["settings_option"] = "the tag database"
            form = DBImportExport()
            template = "dbexport.html"
        case _:
            abort(404)
    if form.validate_on_submit():
        template_context["message"] = "Settings saved"
        match page:
            case "backend":
                assert isinstance(form, BackendSettings)
                conf.set(page, "default_template", form.data["default_template"])
                conf.set(page, "torrent_directories", [x.strip() for x in form.data["torrent_directories"].split(",")])
                conf.set(page, "port", int(form.data["port"]))
                conf.set(page, "title_template", form.data["title_template"])
                conf.set(page, "date_format", form.data["date_format"])
                conf.set(page, "use_preview", form.upload_gif.data)
                conf.set(page, "animated_cover", form.use_gif.data)
                conf.set("metadata", "tag_codec", form.tag_codec.data)
                conf.set("metadata", "tag_date", form.tag_date.data)
                conf.set("metadata", "tag_framerate", form.tag_framerate.data)
                conf.set("metadata", "tag_resolution", form.tag_resolution.data)
                if form.data["media_directory"]:
                    conf.set(page, "media_directory", form.data["media_directory"])
                conf.set(page, "move_method", form.data["move_method"])
                conf.set(page, "anon", form.data["anon"])
                # Show updated title example:
                form.title_example.data = render_template_string(form.title_template.data, **DUMMY_CONTEXT)
            case "images":
                conf.set(page, "upload_gif", form.data["upload_gif"])
                conf.set(page, "use_gif", form.data["use_gif"])
                conf.set(page, "contact_sheet_layout", form.data["contact_sheet_layout"])
                conf.set(page, "num_screens", form.data["num_screens"])
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
            case "rtorrent" | "deluge" | "qbittorrent" | "transmission":
                assert isinstance(form, TorrentSettings)
                path = form.update_self()
                if path:
                    maps:dict = conf.get(page, "pathmaps") # type: ignore
                    del maps[path]
                    if len(maps) > 0:
                        conf.set(page, "pathmaps", maps)
                    else:
                        conf.delete(page, "pathmaps")
                else:
                    conf.set(page, "disable", not form.data["enable_form"])
                    conf.set(page, "host", form.data["host"])
                    conf.set(page, "port", int(form.data["port"]))
                    conf.set(page, "ssl", form.data["ssl"])
                    if "path" in form.data:
                        conf.set(page, "path", form.data["path"])
                    if "username" in form.data and form.data["username"]:
                        conf.set(page, "username", form.data["username"])
                    else:
                        conf.delete(page, "username")
                    if form.data["password"]:
                        conf.set(page, "password", form.data["password"])
                    else:
                        conf.delete(page, "password")
                    if "label" in form.data and form.data["label"]:
                        conf.set(page, "label", form.data["label"])
                    else:
                        conf.delete(page, "label")
                    maps = {}
                    for field in form.file_maps:
                        if field["local_path"].data and field["remote_path"].data:
                            maps[field["local_path"].data] = field["remote_path"].data
                    if len(maps) > 0:
                        conf.set(page, "pathmaps", maps)
                conf.configure_torrents()
            case "files":
                del template_context["message"]
                assert isinstance(form, FileMapForm)
                map = form.update_self()
                if map:
                    conf.delete_subkey("stash", "maps", map)
                elif form.submit.data:
                    template_context["message"] = "Settings saved"
                    if "stash" in conf.conf and "maps" in conf.conf["stash"]:
                        conf.conf["stash"]["maps"].clear()  # type: ignore
                    for map in form.file_maps:
                        conf.set_subkey("stash", "maps", map.data["remote_path"], map.data["local_path"])
            case "hamster":
                assert isinstance(form, HamsterForm)
                if form.submit.data:
                    template_context["message"] = "Settings saved"
                    conf.set(page, "api_key", form.data["api_key"])
            case "database":
                del template_context["message"]
                assert isinstance(form, DBImportExport)
                if form.export_database.data:
                    data = json.dumps(to_dict())
                    temp = tempfile.mktemp()
                    with open(temp, "w") as f:
                        f.write(data)
                    return send_file(temp, as_attachment=True, download_name="export.json")
                elif form.imp.data:
                    data = json.loads(form.upload_database.data.read())
                    from_dict(data)
                    template_context["message"] = "Settings imported"
            case _:
                abort(404)
        conf.update_file()
    template_context["form"] = form
    return render_template(template, **template_context)


@settings_page.app_errorhandler(HTTPException)
def handle_exception(e):
    message = e.name
    if e.code == 404:
        message = "The page you were looking for was not found"
    return render_template("error-page.html", code=e.code, message=message), e.code
