from django.urls import re_path
from image_processor.consumers import ImageBatchProgressConsumer

websocket_urlpatterns = [re_path(r"^ws/image/batches/(?P<pk>\d+)/progress/$", ImageBatchProgressConsumer.as_asgi())]
