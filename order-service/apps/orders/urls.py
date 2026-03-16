from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, SellerOrderViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='orders')
router.register(r'seller/orders', SellerOrderViewSet, basename='seller-orders')

# We can alias checkout to orders create
urlpatterns = [
    path('checkout/', OrderViewSet.as_view({'post': 'create'}), name='checkout'),
    path('', include(router.urls)),
]
