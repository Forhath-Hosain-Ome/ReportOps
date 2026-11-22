from typing import Type
from django.db.models import Model

def _get_active_object(model: Type[Model], object_id: int) -> Model:
    """Shared lookup used by every view that needs a mailbox. Raises
    GmailAccount.DoesNotExist rather than returning None, so each view
    doesn't repeat the same None-check/404 dance."""
    return model.objects.get(id=object_id, is_active=True)
