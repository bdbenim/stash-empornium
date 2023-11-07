from typing import Any
from flask import Blueprint, render_template, redirect, abort

from flask_bootstrap import SwitchField

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, URLField, widgets
from wtforms.validators import DataRequired, Optional, URL, StopValidation, ValidationError

from utils.confighandler import ConfigHandler


conf = ConfigHandler()

settings_page = Blueprint("settings_page", __name__, template_folder="templates")


@settings_page.route("/", methods=["GET"])
def index():
    return redirect("/settings/backend")


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
                anon=conf.get(page, "anon", False),
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


class PasswordField(StringField):
    """
    Original source: https://github.com/wtforms/wtforms/blob/2.0.2/wtforms/fields/simple.py#L35-L42

    A StringField, except renders an ``<input type="password">``.
    Also, whatever value is accepted by this field is not rendered back
    to the browser like normal fields.
    """

    widget = widgets.PasswordInput(hide_value=False)


class PortRange:
    def __init__(self, min=0, max=65535, message=None) -> None:
        self.min = min
        self.max = max
        if not message:
            message = f"Value must be an integer between {min} and {max}"
        self.message = message

    def __call__(self, form, field) -> Any:
        try:
            value = int(field.data)
            assert value >= self.min and value <= self.max
        except:
            raise ValidationError(self.message)


class ConditionallyRequired:
    def __init__(self, fieldname="enable_form", message="This field is required") -> None:
        self.fieldname = fieldname
        self.message = message

    def __call__(self, form, field) -> Any:
        if form.data[self.fieldname]:
            if len(field.data) == 0:
                raise ValidationError(self.message)
        else:
            field.errors[:] = []
            raise StopValidation()


class BackendSettings(FlaskForm):
    default_template = SelectField("Default Template", choices=[opt for opt in conf["templates"]])  # type: ignore
    torrent_directories = StringField("Torrent Directories")
    port = StringField("Port", validators=[PortRange(1024), DataRequired()])
    date_format = StringField()
    title_template = StringField()
    anon = SwitchField("Upload Anonymously")
    save = SubmitField()


class RedisSettings(FlaskForm):
    enable_form = SwitchField("Use Redis")
    host = StringField()
    port = StringField(validators=[PortRange(), ConditionallyRequired()])
    username = StringField(validators=[Optional()])
    password = PasswordField(validators=[Optional()])
    ssl = SwitchField("SSL")
    save = SubmitField()

    # def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
    #     if self.data['enable_form']:
    #         if not (self.data['host'] and self.data['port']):
    #             return False
    #     return super().validate(extra_validators)


class RTorrentSettings(FlaskForm):
    enable_form = SwitchField("Use rTorrent")
    host = StringField(validators=[ConditionallyRequired()])
    port = StringField(validators=[PortRange(), ConditionallyRequired()])
    path = StringField(validators=[ConditionallyRequired("Please specify the API path (typically XMLRPC or RPC2)")])
    username = StringField(validators=[Optional()])
    password = PasswordField(validators=[Optional()])
    label = StringField()
    ssl = SwitchField("SSL")
    save = SubmitField()


class QBittorrentSettings(FlaskForm):
    enable_form = SwitchField("Use qBittorrent", default=("redis" in conf))
    host = StringField(validators=[ConditionallyRequired()])
    port = StringField(validators=[PortRange(), ConditionallyRequired()])
    username = StringField(validators=[Optional()])
    password = PasswordField(validators=[Optional()])
    label = StringField()
    ssl = SwitchField("SSL")
    save = SubmitField()


class DelugeSettings(FlaskForm):
    enable_form = SwitchField("Use Deluge")
    host = StringField(validators=[ConditionallyRequired()])
    port = StringField(validators=[PortRange(), ConditionallyRequired()])
    password = PasswordField(validators=[Optional()])  # type: ignore
    ssl = SwitchField("SSL")
    save = SubmitField()


class StashSettings(FlaskForm):
    url = URLField("URL", validators=[URL(require_tld=False), DataRequired()])
    api_key = PasswordField("API Key", validators=[Optional()])
    save = SubmitField()
