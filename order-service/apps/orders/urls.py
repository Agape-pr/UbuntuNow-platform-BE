from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, SellerOrderViewSet, InternalOrderViewSet, AdminOrderViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='orders')
router.register(r'seller/orders', SellerOrderViewSet, basename='seller-orders')
router.register(r'admin/orders', AdminOrderViewSet, basename='admin-orders')
router.register(r'internal', InternalOrderViewSet, basename='internal-orders')

# We can alias checkout to avoid the 'orders/orders/' double prefix
urlpatterns = [
    path('checkout/', OrderViewSet.as_view({'post': 'create'}), name='checkout'),
    path('', include(router.urls)),
]
