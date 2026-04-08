from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404

from .models import Product
from .serializers import ProductSerializer, ProductCreateUpdateSerializer



class IsSeller(permissions.BasePermission):
    """
    Allows access only to authenticated sellers.
    We verify the role and fetch the store_id entirely statelessly from the JWT payload.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if not getattr(request.user, 'role', None) == 'seller':
            return False

        # Safely extract store_id from the stateless JWT user object
        store = getattr(request.user, 'store', None)
        if store and hasattr(store, 'id') and store.id:
            request.store_id = store.id
            return True
        
        # If the JWT token does not physically have the store_id payload injected, 
        # we reject the request. The user must logout and re-login to generate a new token 
        # using the patched auth-service.
        print(f"Error checking store permission: Missing store_id in JWT. User {request.user.id} needs to authenticate again.")
        return False


class SellerProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsSeller]
    lookup_field = "id"

    def get_serializer_class(self):
        # Use the write serializer for create/update actions only.
        # Use the full read serializer (with images) for list/retrieve.
        if self.action in ('create', 'update', 'partial_update'):
            return ProductCreateUpdateSerializer
        return ProductSerializer

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
        "store_id": ["exact"],
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
