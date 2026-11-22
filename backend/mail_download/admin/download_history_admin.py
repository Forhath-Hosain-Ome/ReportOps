from django.contrib import admin
from mail_download.models import DownloadHistory

@admin.register(DownloadHistory)
class DownloadHistoryAdmin(admin.ModelAdmin):
    """Read-only audit trail. No create/edit/delete via admin."""
    list_display = ("filename", "account", "created_by", "status", "created_at")
    list_filter = ("status", "account")
    search_fields = ("filename", "message_id", "created_by__username", "created_by__email")
    date_hierarchy = "created_at"
    readonly_fields = ("created_by", "account", "message_id", "attachment_id", "filename", "status", "error", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Allow delete for retention/cleanup, superusers only -- flip to
        # False if purges should only happen via a management command.
        return request.user.is_superuser
    