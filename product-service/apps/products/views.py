from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404

from .models import Product
from .serializers import ProductSerializer, ProductCreateUpdateSerializer



class IsSeller(permissions.BasePermission):
    """
    Allows access only to authenticated sellers.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_seller()


class SellerProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSeller]
    serializer_class = ProductCreateUpdateSerializer
    lookup_field = "id"

    def get_queryset(self):
        return (
            Product.objects
            .filter(store__user=self.request.user)
            .select_related("category", "store")
            .prefetch_related("images")
        )

    def perform_create(self, serializer):
        serializer.save(store_id=self.request.user.store.id if self.request.user.store else None)


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
            .select_related("category", "store")
            .prefetch_related("images")
        )



# views.py
from rest_framework import viewsets
from .models import Category
from .serializers import CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
