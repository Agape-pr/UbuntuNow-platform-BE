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
            
        # Fallback: if store_id is missing from JWT (e.g. timeout during token generation or old token),
        # fetch it directly from store-service
        import os
        import requests
        try:
            store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')
            res = requests.get(f"{store_url}/api/v1/users/internal/stores/{request.user.id}/", timeout=2)
            if res.status_code == 200:
                store_data = res.json()
                if store_data.get('id'):
                    request.store_id = store_data.get('id')
                    return True
        except Exception as e:
            print(f"Fallback store_id fetch failed: {e}")
        
        # If we still can't find the store_id, reject the request.
        print(f"Error checking store permission: Missing store_id in JWT and fallback failed. User {request.user.id} needs to authenticate again.")
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

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        if str(lookup_value).isdigit():
            obj = get_object_or_404(queryset, id=lookup_value)
        else:
            obj = get_object_or_404(queryset, **{self.lookup_field: lookup_value})

        self.check_object_permissions(self.request, obj)
        return obj


# views.py
from rest_framework import viewsets
from .models import Category
from .serializers import CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

@api_view(['PATCH'])
@permission_classes([permissions.AllowAny])
def update_stock_internal(request, id):
    # This endpoint is only called internally by order-service to deduct stock
    # bypassing the IsSeller permission check.
    product = get_object_or_404(Product, id=id)
    new_stock = request.data.get('stock_quantity')
    if new_stock is not None:
        product.stock_quantity = new_stock
        product.save()
        return Response({'status': 'stock updated', 'new_stock': product.stock_quantity})
    return Response({'error': 'stock_quantity required'}, status=400)
