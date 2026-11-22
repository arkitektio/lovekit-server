"""Admin configuration for the bridge app."""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

# Register your models here.
from bridge import models


class HistoryAdmin(SimpleHistoryAdmin):  # type: ignore
    """Admin class for models that use simple_history."""

    list_display = ["id"]


admin.site.register(models.Agent)
admin.site.register(models.Stream)
