from flask_bootstrap import SwitchField
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    Form,
    FieldList,
    FormField,
    SelectField,
    StringField,
    SubmitField,
    URLField,
    SelectMultipleField, IntegerField,
)
from wtforms.validators import URL, DataRequired, Optional
from wtforms.widgets import Input, PasswordInput

from utils.db import StashTag, Category
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


class FileMap(Form):
    local_path = StringField(
        render_kw={"data-toggle": "tooltip", "title": "This is the path as stash-empornium sees it"}
    )
    remote_path = StringField()
    delete = SubmitField()


class BackendSettings(FlaskForm):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "choices" in kwargs:
            self.default_template.choices = kwargs["choices"]

    default_template = SelectField("Default Template")
    torrent_directories = StringField("Torrent Directories", render_kw={"placeholder": ""})
    port = StringField("Port", validators=[PortRange(1024), DataRequired()])
    date_format = StringField()
    date_example = StringField("Date Example", render_kw={"readonly": True})
    title_template = StringField()
    title_example = StringField("Title Example", render_kw={"readonly": True})
    anon = SwitchField("Upload Anonymously")
    media_directory = StringField(
        validators=[Directory()],
        render_kw={"data-toggle": "tooltip", "title": "Where to save data for multi-file torrents"},
    )
    move_method = SelectField(choices=["copy", "hardlink", "symlink"])  # type: ignore
    tag_codec = SwitchField()
    tag_date = SwitchField()
    tag_framerate = SwitchField()
    tag_resolution = SwitchField()
    save = SubmitField()

class ImageSettings(FlaskForm):
    upload_gif = SwitchField("Upload Preview GIF")
    use_gif = SwitchField("Use GIF as Cover")
    contact_sheet_layout = StringField()
    num_screens = IntegerField()
    save = SubmitField()

class RedisSettings(FlaskForm):
    enable_form = SwitchField("Use Redis")
    host = StringField()
    port = StringField(validators=[PortRange(), ConditionallyRequired()])
    username = StringField(validators=[Optional()])
    password = PasswordField(validators=[Optional()])
    ssl = SwitchField("SSL")
    save = SubmitField()


class TorrentSettings(FlaskForm):
    enable_form = SwitchField("Enable")
    host = StringField(validators=[ConditionallyRequired()])
    port = StringField(validators=[PortRange(), ConditionallyRequired()])
    path = StringField(
        validators=[ConditionallyRequired(message="Please specify the API path (typically XMLRPC or RPC2)")]
    )
    username = StringField(validators=[Optional()])
    password = PasswordField(validators=[Optional()])
    label = StringField()
    ssl = SwitchField("SSL")
    file_maps = FieldList(FormField(FileMap, "File Map"))
    new_map = SubmitField()
    save = SubmitField()

    def __init__(self, *args, **kwargs):
        maps = []
        if "maps" in kwargs:
            for local, remote in kwargs["maps"].items():
                maps.append({"local_path": local, "remote_path": remote})
            kwargs["file_maps"] = maps
        super().__init__(*args, **kwargs)
        for map in self.file_maps.entries:
            map["remote_path"].render_kw = {
                "data-toggle": "tooltip",
                "title": "This is the path as rTorrent sees it",
            }

    def update_self(self):
        map = None

        # read the data in the form
        read_form_data = self.data

        # modify the data:
        updated_list = read_form_data["file_maps"]
        if read_form_data["new_map"]:
            updated_list.append({})
        else:
            for i, row in enumerate(read_form_data["file_maps"]):
                if row["delete"]:
                    del updated_list[i]
                    map = row["local_path"]
        read_form_data["file_maps"] = updated_list

        # reload the form from the modified data
        self.__init__(formdata=None, **read_form_data)
        self.validate()  # the errors on validation are cancelled in the line above
        return map


class RTorrentSettings(TorrentSettings):
    pass


class QBittorrentSettings(TorrentSettings):
    path = None


class DelugeSettings(TorrentSettings):
    username = None
    label = None
    path = None


class TransmissionSettings(TorrentSettings):
    pass


class StashSettings(FlaskForm):
    url = URLField("URL", validators=[URL(require_tld=False), DataRequired()])
    api_key = PasswordField("API Key", validators=[Optional()])
    save = SubmitField()


class TagMap(Form):
    stash_tag = StringField()
    emp_tag = StringField("EMP Tag", validators=[Tag()])
    advanced = SubmitField()
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

        # modify the data:
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
        return tag


def getCategories():
    return [cat.name for cat in Category.query.all()]


class TagAdvancedForm(FlaskForm):
    ignored = SwitchField(
        render_kw={
            "data-toggle": "tooltip",
            "title": "Don't include this tag in uploads",
        }
    )
    stash_tag = StringField(
        validators=[DataRequired()],
        render_kw={
            "data-toggle": "tooltip",
            "title": "The name of the tag in your stash server",
        },
    )
    display = StringField(
        render_kw={
            "data-toggle": "tooltip",
            "title": "(Optional) How you want this tag to be displayed in your presentation",
        }
    )
    def_tags = StringField(
        "Default Tags",
        render_kw={
            "data-toggle": "tooltip",
            "title": "(Optional) The tag(s) that this will correspond to on any tracker that does not have its own tags set",
        },
    )
    emp_tags = StringField(
        "EMP Tags",
        render_kw={
            "data-toggle": "tooltip",
            "title": "(Optional) The tag(s) that this corresponds to on Empornium",
        },
    )
    pb_tags = StringField(
        "PB Tags",
        render_kw={
            "data-toggle": "tooltip",
            "title": "(Optional) The tag(s) that this corresponds to on Pornbay",
        },
    )
    fc_tags = StringField(
        "FC Tags",
        render_kw={
            "data-toggle": "tooltip",
            "title": "(Optional) The tag(s) that this corresponds to on Femdom Cult",
        },
    )
    ent_tags = StringField(
        "ENT Tags",
        render_kw={
            "data-toggle": "tooltip",
            "title": "(Optional) The tag(s) that this corresponds to on Enthralled",
        },
    )
    hf_tags = StringField(
        "HF Tags",
        render_kw={
            "data-toggle": "tooltip",
            "title": "(Optional) The tag(s) that this corresponds to on Happy Fappy",
        },
    )
    categories = SelectMultipleField(choices=getCategories)  # type: ignore
    delete = SubmitField()
    save = SubmitField()

    def __init__(self, *args, **kwargs):
        if "tag" in kwargs:
            tag: StashTag = kwargs["tag"]
            kwargs["stash_tag"] = tag.tagname
            kwargs["def_tags"] = " ".join([et.tagname for et in tag.def_tags])
            kwargs["emp_tags"] = " ".join([et.tagname for et in tag.emp_tags])
            kwargs["pb_tags"] = " ".join([et.tagname for et in tag.pb_tags])
            kwargs["fc_tags"] = " ".join([et.tagname for et in tag.fc_tags])
            kwargs["ent_tags"] = " ".join([et.tagname for et in tag.ent_tags])
            kwargs["hf_tags"] = " ".join([et.tagname for et in tag.hf_tags])
            kwargs["display"] = tag.display
            kwargs["categories"] = [cat.name for cat in tag.categories]
            kwargs["ignored"] = tag.ignored
        super().__init__(*args, **kwargs)


class CategoryForm(Form):
    name = StringField()
    delete = SubmitField()


class CategoryList(FlaskForm):
    categories = FieldList(FormField(CategoryForm))
    new_category = SubmitField()
    submit = SubmitField()

    def __init__(self, *args, **kwargs):
        if "category_objs" in kwargs:
            kwargs["categories"] = [{"name": cat.name} for cat in kwargs["category_objs"]]
        super().__init__(*args, **kwargs)

    def update_self(self):
        category = None

        # read the data in the form
        read_form_data = self.data

        # modify the data:
        updated_list = read_form_data["categories"]
        if self.new_category.data:
            updated_list.append({})
        else:
            for i, row in enumerate(read_form_data["categories"]):
                if row["delete"]:
                    del updated_list[i]
                    category = row["name"]
        read_form_data["categories"] = updated_list

        # reload the form from the modified data
        self.__init__(formdata=None, **read_form_data)
        self.validate()  # the errors on validation are cancelled in the line above
        return category


class HamsterForm(FlaskForm):
    api_key = StringField(
        "API Key"
    )
    submit = SubmitField()


class SearchResult(Form):
    stash_tag = StringField(render_kw={"readonly": True})
    emp_tag = StringField("EMP Tag", render_kw={"readonly": True})
    settings = SubmitField()


class SearchForm(FlaskForm):
    tags = FieldList(FormField(SearchResult, render_kw={"readonly": True}))

    def __init__(self, *args, **kwargs):
        tags = []
        if "s_tags" in kwargs:
            for stag in kwargs["s_tags"]:
                etag = " ".join([et.tagname for et in stag.emp_tags])
                tags.append({"stash_tag": stag.tagname, "emp_tag": etag})
            kwargs["tags"] = tags
        super().__init__(*args, **kwargs)


class FileMapForm(FlaskForm):
    file_maps = FieldList(FormField(FileMap, "File Maps"))
    new_map = SubmitField()
    submit = SubmitField()

    def __init__(self, *args, **kwargs):
        maps = []
        if "maps" in kwargs and kwargs["maps"] is not None:
            for remote, local in kwargs["maps"].items():
                maps.append({"local_path": local, "remote_path": remote})
            kwargs["file_maps"] = maps
        super().__init__(*args, **kwargs)

    def update_self(self):
        map = None

        # read the data in the form
        read_form_data = self.data

        # modify the data:
        updated_list = read_form_data["file_maps"]
        if read_form_data["new_map"]:
            updated_list.append({})
        else:
            for i, row in enumerate(read_form_data["file_maps"]):
                if row["delete"]:
                    del updated_list[i]
                    map = row["local_path"]
        read_form_data["file_maps"] = updated_list

        # reload the form from the modified data
        self.__init__(formdata=None, **read_form_data)
        self.validate()  # the errors on validation are cancelled in the line above
        return map


class DBImportExport(FlaskForm):
    export_database = SubmitField()
    upload_database = FileField(validators=[FileAllowed(["txt", "json", "md"])])
    imp = SubmitField("Import")
