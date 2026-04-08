from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Store

User = get_user_model()

class StoreSerializer(serializers.ModelSerializer):
    store_logo = serializers.SerializerMethodField()
    store_description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )

    def get_store_logo(self, obj):
        if not obj.store_logo:
            return None
        try:
            return obj.store_logo.url
        except Exception:
            return str(obj.store_logo)

    class Meta:
        model = Store
        fields = ['id', 'user_id', 'store_name', 'slug', 'store_description', 'store_logo']

    def to_internal_value(self, data):
        # Normalize empty strings to None for optional fields
        if 'store_description' in data and data['store_description'] == '':
            data['store_description'] = None
        return super().to_internal_value(data)

class PublicStoreSerializer(serializers.ModelSerializer):
    products = serializers.SerializerMethodField()
    store_logo = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = ['store_name', 'slug', 'store_description', 'store_logo', 'created_at', 'products']

    def get_store_logo(self, obj):
        if not obj.store_logo:
            return None
        try:
            return obj.store_logo.url
        except Exception:
            return str(obj.store_logo)

    def get_products(self, obj):
        """
        Fetch active products for this store from the product-service over HTTP.
        The store-service and product-service are separate containers — we cannot
        import from each other's code directly.
        """
        import requests
        import os
        product_service_url = os.environ.get('PRODUCT_SERVICE_URL', 'http://localhost:8003')
        try:
            res = requests.get(
                f"{product_service_url}/api/v1/products/products/",
                params={'store_id': obj.user_id},
                timeout=5,
            )
            if res.status_code == 200:
                data = res.json()
                # Handle both paginated {results:[...]} and plain list responses
                if isinstance(data, dict) and 'results' in data:
                    return data['results']
                return data
        except Exception:
            pass
        return []
