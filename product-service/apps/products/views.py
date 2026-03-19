from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404

from .models import Product
from .serializers import ProductSerializer, ProductCreateUpdateSerializer



class IsSeller(permissions.BasePermission):
    """
    Allows access only to authenticated sellers.
    We verify the role from the JWT and fetch the store_id from the store-service.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if not request.user.role == 'seller':
            return False

        import requests
        import os
        store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')
        try:
            res = requests.get(f"{store_url}/api/v1/users/internal/stores/{request.user.id}/", timeout=2)
            if res.status_code == 200:
                request.store_id = res.json().get('id')
                return True
        except Exception as e:
            print(f"Error checking store permission: {e}")
        return False


class SellerProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSeller]
    serializer_class = ProductCreateUpdateSerializer
    lookup_field = "id"

    def get_queryset(self):
        store_id = getattr(self.request, 'store_id', None)
        if not store_id:
            return Product.objects.none()
            
        return (
            Product.objects
            .filter(store_id=store_id)
            .select_related("category")
            .prefetch_related("images")
        )

    def perform_create(self, serializer):
        store_id = getattr(self.request, 'store_id', None)
        serializer.save(store_id=store_id)


class PublicProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    filterset_fields = {
        "category__slug": ["exact"],
        "store__id": ["exact"],
        "price": ["gte", "lte"],
    }

    search_fields = ["name", "description", "category__name",
    "category__slug"]
    ordering_fields = ["price", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Product.objects
            .filter(is_active=True)
            .select_related("category")
            .prefetch_related("images")
        )



# views.py
from rest_framework import viewsets
from .models import Category
from .serializers import CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
