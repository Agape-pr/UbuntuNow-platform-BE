import logging

from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404

from .models import Product
from .serializers import ProductSerializer, ProductCreateUpdateSerializer
from shared.core.utils.internal import IsInternalService, internal_headers



logger = logging.getLogger(__name__)


class IsSeller(permissions.BasePermission):
    """
    Allows access only to authenticated sellers.
    We verify the role and fetch the store_id entirely statelessly from the JWT payload.
    """

    def has_permission(self, request, view):
        import os
        import requests as http_requests

        if not request.user or not request.user.is_authenticated:
            logger.debug("IsSeller: rejected, user not authenticated")
            return False

        role = getattr(request.user, 'role', None)
        if role != 'seller':
            logger.info("IsSeller: rejected, role is %r not 'seller'", role)
            return False

        # 1️⃣ Try store_id directly from the JWT StatelessUser object
        store = getattr(request.user, 'store', None)
        store_id = getattr(store, 'id', None) if store else None

        if store_id:
            request.store_id = store_id
            logger.debug("IsSeller: approved, store_id=%s from JWT", store_id)
            return True

        # 2️⃣ Fallback: JWT was issued before store was created OR store_id missing.
        #    Hit the store-service internal API to resolve it.
        user_id = getattr(request.user, 'id', None)
        logger.info("IsSeller: store_id missing in JWT for user %s, looking it up", user_id)

        store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')
        try:
            res = http_requests.get(
                f"{store_url}/api/v1/users/internal/stores/{user_id}/",
                headers=internal_headers(),
                timeout=3,
            )
            logger.debug("IsSeller: store-service responded %s", res.status_code)
            if res.status_code == 200:
                store_data = res.json()
                # Must use Store.id (PK), NOT user_id — products are indexed by Store.id
                store_id = store_data.get('id')
                if store_id:
                    request.store_id = store_id
                    logger.debug("IsSeller: approved via fallback, store_id=%s", store_id)
                    return True
                logger.warning("IsSeller: store-service returned no id for user %s", user_id)
        except Exception as e:
            logger.warning("IsSeller: store lookup failed: %s", e)

        logger.warning("IsSeller: rejected, could not resolve store_id for user %s (STORE_SERVICE_URL=%s). "
                       "Seller must log out and log back in.", user_id, store_url)
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
        "category": ["exact"],
        "store_id": ["exact"],
        "price": ["gte", "lte"],
    }

    search_fields = ["name", "description", "category"]
    ordering_fields = ["price", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Product.objects
            .filter(is_active=True)
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


from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

@api_view(['PATCH'])
@permission_classes([IsInternalService])
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
