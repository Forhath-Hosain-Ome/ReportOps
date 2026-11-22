from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('inspection-summary/', include('inspection_summary.urls', namespace='inspection_summary')),

    path("auth/token/",         TokenObtainPairView.as_view(), name="token_obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(),    name="token_refresh"),

    path("puma/", include("puma_summary.urls", namespace="puma_summary")),
    path("image/", include("image_processor.urls", namespace="image_processor")),
    path("final-summary/", include("final_summary.urls", namespace="final_summary")),
    path("top-five/", include("top_five.urls", namespace="top_five")),
    path("mail-fetch/", include("mail_download.urls", namespace="mail_download")),
]

#192.168.0.1:8080/puma/batches/upload/