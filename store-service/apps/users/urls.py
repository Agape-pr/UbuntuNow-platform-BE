from django.urls import path
from .views import InternalStoreCreateView, InternalStoreRetrieveView, PublicStoreView, UpdateStoreView

urlpatterns = [
    path('internal/stores/', InternalStoreCreateView.as_view()),
    path('internal/stores/<int:user_id>/', InternalStoreRetrieveView.as_view()),
    path('store/me/', UpdateStoreView.as_view(), name='update-my-store'),
    path('store/<slug:slug>/', PublicStoreView.as_view(), name='public-store'),
]
