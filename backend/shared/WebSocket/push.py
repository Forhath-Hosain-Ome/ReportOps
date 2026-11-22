import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

def _push(group: str, message: dict) -> None:
    try:
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(group, message)
    except Exception as exc:
        logger.debug("WS push failed: %s", exc)