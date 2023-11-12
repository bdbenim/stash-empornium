import re
import os
from wtforms.validators import StopValidation, ValidationError

class PortRange:
    def __init__(self, min=0, max=65535, message=None) -> None:
        self.min = min
        self.max = max
        if not message:
            message = f"Value must be an integer between {min} and {max}"
        self.message = message

    def __call__(self, form, field) -> None:
        try:
            value = int(field.data)
            assert value >= self.min and value <= self.max
        except:
            raise ValidationError(self.message)


class ConditionallyRequired:
    def __init__(self, fieldname="enable_form", message="This field is required") -> None:
        self.fieldname = fieldname
        self.message = message

    def __call__(self, form, field) -> None:
        if form.data[self.fieldname]:
            if len(field.data) == 0:
                raise ValidationError(self.message)
        else:
            field.errors[:] = []
            raise StopValidation()


class Directory:
    def __call__(self, form, field) -> None:
        dir: str = field.data
        try:
            if dir and os.path.isfile(dir):
                raise ValidationError("Must be a directory")
        except:
            raise ValidationError("Must be a directory")

class Tag:
    def __call__(self, form, field) -> None:
        if not field.data:
            return
        tags:list[str] = field.data.split()
        for tag in tags:
            if len(tag) > 32:
                raise ValidationError(f"Tags must not exceed 32 characters")
            if tag.startswith(".") or tag.endswith("."):
                raise ValidationError("Tags cannot start or end with a period")
            result = re.fullmatch(r"[\.\w]+", tag)
            if not result:
                raise ValidationError("Tags must only contain letters, numbers, and periods")
        result = re.match(r".*\.\.", field.data)
        if result:
            raise ValidationError("Tags cannot contain consecutive periods")
