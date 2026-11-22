from django.urls import include, path

urlpatterns = [path("image/", include("image_processor.urls"))]
