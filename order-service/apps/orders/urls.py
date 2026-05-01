from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, SellerOrderViewSet

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='orders')
router.register(r'seller/orders', SellerOrderViewSet, basename='seller-orders')

# We can alias checkout and mock-payment to avoid the 'orders/orders/' double prefix
urlpatterns = [
    path('checkout/', OrderViewSet.as_view({'post': 'create'}), name='checkout'),
    path('<int:pk>/mock-payment/', OrderViewSet.as_view({'post': 'mock_payment'}), name='mock-payment'),
    path('', include(router.urls)),
]
