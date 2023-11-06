from collections.abc import Mapping, Sequence
from typing import Any
from flask import Blueprint, render_template, redirect, url_for, send_from_directory

from flask_bootstrap import SwitchField, HiddenField

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, FormField, URLField, IntegerField, widgets
from wtforms.validators import DataRequired, Length, NumberRange, Optional, URL, ValidationError

from utils.confighandler import ConfigHandler

import re

conf = ConfigHandler()

simple_page = Blueprint("simple_page", __name__, template_folder="templates")


@simple_page.route("/", methods=["GET"])
def index():
    return redirect("/settings/backend")


@simple_page.route("/settings/<page>", methods=["GET", "POST"])
def settings(page):
    template_context = {}
    match page:
        case "backend":
            template_context["settings_option"] = "your stash-empornium backend"
            form = BackendSettings()
        case "stash":
            template_context["settings_option"] = "your stash server"
            form = StashSettings()
        case "redis":
            template_context["settings_option"] = "your redis server"
            form = RedisSettings()
        case "rtorrent":
            template_context["settings_option"] = "your rTorrent client"
            form = RTorrentSettings()
        case "deluge":
            template_context["settings_option"] = "your Deluge client"
            form = DelugeSettings()
        case "qbittorrent":
            template_context["settings_option"] = "your qBittorrent client"
            form = QBittorrentSettings()
        case _:
            template_context["settings_option"] = "your stash-empornium backend"
            form = SettingsForm()
    if form.validate_on_submit():
        if form.data['formid'] == 'redis':
            print('Redis settings')
            print(form.data)
    template_context['form'] = form
    return render_template("index.html", **template_context)

class SEForm(FlaskForm):
    formid = HiddenField()

class PasswordField(StringField):
    """
    Original source: https://github.com/wtforms/wtforms/blob/2.0.2/wtforms/fields/simple.py#L35-L42

    A StringField, except renders an ``<input type="password">``.
    Also, whatever value is accepted by this field is not rendered back
    to the browser like normal fields.
    """
    widget = widgets.PasswordInput(hide_value=False)

def Integer(form, field):
    if not re.match(r"^\d+$", field.data):
        raise ValidationError("Input must be an integer")
    
class PortRange():
    def __init__(self, min=0, max=65535, message=None) -> None:
        self.min = min
        self.max = max
        if not message:
            message = f"Value must be an integer between {min} and {max}"
        self.message = message
    
    def __call__(self, form, field) -> Any:
        if not re.match(r"^\d+$", field.data):
            raise ValidationError(self.message)
        if int(field.data) < self.min or int(field.data) > self.max:
            raise ValidationError(self.message)

class BackendSettings(SEForm):
    formid = HiddenField(default="backend")
    default_template = SelectField("Default Template", choices=[opt for opt in conf["templates"]])  # type: ignore
    torrent_directories = StringField("Torrent Directories")
    port = StringField("Port", validators=[PortRange(1024)])
    date_format = StringField()
    title_template = StringField()
    anon = SwitchField("Upload Anonymously")
    submit = SubmitField()


class RedisSettings(SEForm):
    formid = HiddenField(default="redis")
    enable_form = SwitchField("Use Redis",default=("redis" in conf))
    host = StringField(default=conf.get("redis", "host", ""))  # type: ignore
    port = StringField(default=conf.get("redis", "port", ""), validators=[PortRange(), Optional()])  # type: ignore
    username = StringField(default=conf.get("redis", "username", ""), validators=[Optional()])  # type: ignore
    password = PasswordField(default=conf.get("redis", "password", ""), validators=[Optional()])  # type: ignore
    ssl = SwitchField("SSL", default=conf.get("redis", "ssl", False))
    submit = SubmitField()


class RTorrentSettings(SEForm):
    formid = HiddenField(default="rtorrent")
    enable_form = SwitchField("Use rTorrent",default=("redis" in conf))
    host = StringField(default=conf.get("rtorrent", "host", ""))  # type: ignore
    port = StringField(default=conf.get("rtorrent", "port", ""), validators=[PortRange(), Optional()])  # type: ignore
    path = StringField(default=conf.get("rtorrent", "path", ""))  # type: ignore
    username = StringField(default=conf.get("rtorrent", "username", ""), validators=[Optional()])  # type: ignore
    password = PasswordField(default=conf.get("rtorrent", "password", ""), validators=[Optional()])  # type: ignore
    label = StringField(default=conf.get("rtorrent", "label", ""))  # type: ignore
    ssl = SwitchField("SSL", default=conf.get("rtorrent", "ssl", False))


class QBittorrentSettings(SEForm):
    formid = HiddenField(default="qbittorrent")
    enable_form = SwitchField("Use qBittorrent",default=("redis" in conf))
    host = StringField(default=conf.get("qbittorrent", "host", ""))  # type: ignore
    port = StringField(default=conf.get("qbittorrent", "port", ""), validators=[PortRange(), Optional()])  # type: ignore
    username = StringField(default=conf.get("qbittorrent", "username", ""), validators=[Optional()])  # type: ignore
    password = PasswordField(default=conf.get("qbittorrent", "password", ""), validators=[Optional()])  # type: ignore
    label = StringField(default=conf.get("qbittorrent", "label", ""))  # type: ignore
    ssl = SwitchField("SSL", default=conf.get("qbittorrent", "ssl", False))


class DelugeSettings(SEForm):
    formid = HiddenField(default="deluge")
    enable_form = SwitchField("Use Deluge",default=("redis" in conf))
    host = StringField(default=conf.get("deluge", "host", ""))  # type: ignore
    port = StringField(default=conf.get("deluge", "port", ""), validators=[PortRange(), Optional()])  # type: ignore
    password = PasswordField(default=conf.get("deluge", "password", ""), validators=[Optional()])  # type: ignore
    ssl = SwitchField("SSL", default=conf.get("deluge", "ssl", False))


class StashSettings(SEForm):
    formid = HiddenField(default="stash")
    url = URLField("URL", default=conf.get("stash", "url", ""), validators=[URL(require_tld=False), DataRequired()])  # type: ignore
    api_key = PasswordField("API Key", default=conf.get("stash", "api_key", ""), validators=[Optional()])  # type: ignore
    submit = SubmitField()


class SettingsForm(SEForm):
    backend = FormField(BackendSettings)
    stash = FormField(StashSettings)
    if "redis" in conf:
        redis = FormField(RedisSettings)
