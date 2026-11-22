from django.urls import include, path

urlpatterns = [path("inspection-summary/", include("inspection_summary.urls"))]
