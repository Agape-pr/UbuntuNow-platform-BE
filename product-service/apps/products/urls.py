from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SellerProductViewSet, PublicProductViewSet
from .views import CategoryViewSet



router = DefaultRouter()
router.register(r'seller/products', SellerProductViewSet, basename='seller-products')
router.register(r'products', PublicProductViewSet, basename='public-products')
router.register(r'categories', CategoryViewSet, basename='category')
urlpatterns = [
    path('', include(router.urls)),
]
