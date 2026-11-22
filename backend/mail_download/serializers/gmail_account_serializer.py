from rest_framework import serializers
from mail_download.models import GmailAccount


class GmailAccountSerializer(serializers.ModelSerializer):
    """Powers the mailbox dropdown. Token fields are deliberately absent
    from `fields` -- not read_only, not excluded in to_representation(),
    just never named here at all."""
    class Meta:
        model = GmailAccount
        fields = ["id", "email_address", "label", "is_active", "last_used_at"]
        read_only_fields = fields  # nothing about this resource is editable via the API

