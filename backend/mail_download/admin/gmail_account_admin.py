
from django.contrib import admin
from django.utils.html import format_html

from mail_download.models import GmailAccount


@admin.register(GmailAccount)
class GmailAccountAdmin(admin.ModelAdmin):
    list_display = ("label_or_email", "is_active", "token_status", "created_by",
                     "last_used_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("email_address", "label")
    readonly_fields = ("email_address", "scopes", "token_expiry", "created_by",
                        "created_at", "last_used_at", "token_status")

    # Token fields are intentionally absent from `fields`/`fieldsets` --
    # never rendered in any form, encrypted or not. Re-authorizing a
    # mailbox happens through the OAuth start/callback views, never here.
    fields = ("label", "email_address", "is_active", "token_status",
              "scopes", "token_expiry", "created_by", "created_at", "last_used_at")

    def label_or_email(self, obj):
        return obj.label or obj.email_address
    label_or_email.short_description = "Mailbox"

    def token_status(self, obj):
        """Shows whether a refresh token is present, never the token
        itself. This is the only thing an admin needs to know at a
        glance: 'is this mailbox still authorized or does someone need
        to re-run the OAuth flow.'"""
        ok = bool(obj.refresh_token)
        color = "#2e7d32" if ok else "#c62828"
        text = "Connected" if ok else "Needs reconnect"
        return format_html('<span style="color: {}; font-weight: 600;">{}</span>', color, text)
    token_status.short_description = "OAuth status"

    def has_add_permission(self, request):
        # Block manual creation entirely -- a GmailAccount only ever comes
        # into existence via gmail_oauth.exchange_code_for_account().
        return False

    def get_readonly_fields(self, request, obj=None):
        # Belt-and-suspenders: even if `fields` is edited later to add a
        # token column by mistake, force it read-only too.
        ro = list(super().get_readonly_fields(request, obj))
        return ro

    actions = ["deactivate_accounts", "reactivate_accounts"]

    def deactivate_accounts(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_accounts.short_description = "Deactivate selected mailbox(es)"

    def reactivate_accounts(self, request, queryset):
        queryset.update(is_active=True)
    reactivate_accounts.short_description = "Reactivate selected mailbox(es)"
