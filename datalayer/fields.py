from django.db import models
from django.core.exceptions import ValidationError
import re


def validate_store_path(value: str) -> None:
    """Validate that the value is a supported object-store URI."""
    pattern = r"^(seaweed|s3)://[^/]+/.+"
    if not re.match(pattern, value):
        raise ValidationError(
            "Invalid store path format. Expected seaweed://bucket/object_key",
            code="invalid",
        )


class StorePathField(models.CharField):
    """A CharField to store SeaweedFS-backed object paths."""

    description = "CharField to store object-store paths with validation"

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the field with a default max_length of 500."""
        kwargs["max_length"] = kwargs.get("max_length", 500)
        validators = list(kwargs.get("validators", []))
        if validate_store_path not in validators:
            validators.append(validate_store_path)
        kwargs["validators"] = validators

        super().__init__(*args, **kwargs)

    def deconstruct(self):
        """Strip the internally-added defaults so migrations stay stable.

        ``__init__`` injects ``validate_store_path`` and a default
        ``max_length``; without removing them here they would be re-serialized
        into every migration and re-appended on reconstruction, producing an
        endless stream of no-op "alter field" migrations.
        """
        name, path, args, kwargs = super().deconstruct()
        validators = [v for v in kwargs.get("validators", []) if v is not validate_store_path]
        if validators:
            kwargs["validators"] = validators
        else:
            kwargs.pop("validators", None)
        if kwargs.get("max_length") == 500:
            del kwargs["max_length"]
        return name, path, args, kwargs


S3Field = StorePathField
