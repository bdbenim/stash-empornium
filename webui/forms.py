from typing import Any

from wtforms import StringField, BooleanField
from wtforms.widgets import Input, PasswordInput
from wtforms.validators import StopValidation, ValidationError

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