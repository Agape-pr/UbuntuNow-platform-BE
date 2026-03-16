from django.urls import path, include

urlpatterns = [
    path("otp/", include("apps.authentication.urls.otp")),
]
