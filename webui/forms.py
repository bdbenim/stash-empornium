from flask_bootstrap import SwitchField
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    BooleanField,
    Form,
    FieldList,
    FormField,
    SubmitField,
    SelectField,
    StringField,
    SubmitField,
    URLField,
)
from wtforms.widgets import Input, PasswordInput
from wtforms.validators import URL, DataRequired, Optional
from webui.validators import PortRange, ConditionallyRequired, Directory, Tag


class PasswordField(StringField):
    """
    Original source: https://github.com/wtforms/wtforms/blob/2.0.2/wtforms/fields/simple.py#L35-L42

    A StringField, except renders an ``<input type="password">``.
    Also, whatever value is accepted by this field is not rendered back
    to the browser like normal fields.
    """

    widget = PasswordInput(hide_value=False)


class ButtonInput(Input):
    """
    Renders a button input.

    The field's label is used as the text of the button instead of the
    data on the field.
    """

    input_type = "reset"

    def __call__(self, field, **kwargs):
        kwargs.setdefault("value", field.label.text)
        return super().__call__(field, **kwargs)


class ButtonField(BooleanField):
    """
    Represents an ``<input type="button">``.  This allows checking if a given
    submit button has been pressed.
    """

    widget = ButtonInput()


class BackendSettings(FlaskForm):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "choices" in kwargs:
            self.default_template.choices = kwargs["choices"]

    default_template = SelectField("Default Template")
    torrent_directories = StringField("Torrent Directories", render_kw={"placeholder": ""})
    port = StringField("Port", validators=[PortRange(1024), DataRequired()])
    date_format = StringField()
    example = StringField("Date Example:", render_kw={"readonly": True})
    title_template = StringField()
    anon = SwitchField("Upload Anonymously")
    media_directory = StringField(validators=[Directory()])
    move_method = SelectField(choices=["copy", "hardlink", "symlink"])  # type: ignore
    save = SubmitField()


class RedisSettings(FlaskForm):
    enable_form = SwitchField("Use Redis")
    host = StringField()
    port = StringField(validators=[PortRange(), ConditionallyRequired()])
    username = StringField(validators=[Optional()])
    password = PasswordField(validators=[Optional()])
    ssl = SwitchField("SSL")
    save = SubmitField()


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
    enable_form = SwitchField("Use qBittorrent")
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
    password = PasswordField(validators=[Optional()])
    ssl = SwitchField("SSL")
    save = SubmitField()


class StashSettings(FlaskForm):
    url = URLField("URL", validators=[URL(require_tld=False), DataRequired()])
    api_key = PasswordField("API Key", validators=[Optional()])
    save = SubmitField()


class TagMap(Form):
    stash_tag = StringField()
    emp_tag = StringField("EMP Tag", validators=[Tag()])
    delete = SubmitField()


class TagMapForm(FlaskForm):
    tags = FieldList(FormField(TagMap), min_entries=1)
    submit = SubmitField()
    newline = SubmitField("Add Tag")

    def __init__(self, *args, **kwargs):
        tags = []
        if "s_tags" in kwargs:
            for stag in kwargs["s_tags"]:
                etag = " ".join([et.tagname for et in stag.emp_tags])
                tags.append({"stash_tag": stag.tagname, "emp_tag": etag})
            kwargs["tags"] = tags
        super().__init__(*args, **kwargs)

    def update_self(self):
        tag = None

        # read the data in the form
        read_form_data = self.data

        # modify the data as you see fit:
        updated_list = read_form_data["tags"]
        if read_form_data["newline"]:
            updated_list.append({})
        else:
            for i, row in enumerate(read_form_data["tags"]):
                if row["delete"]:
                    del updated_list[i]
                    tag = row["stash_tag"]
        read_form_data["tags"] = updated_list

        # reload the form from the modified data
        self.__init__(formdata=None, **read_form_data)
        self.validate()  # the errors on validation are cancelled in the line above
        if tag:
            return tag
