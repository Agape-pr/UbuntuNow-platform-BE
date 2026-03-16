from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Store

User = get_user_model()

class StoreSerializer(serializers.ModelSerializer):
    store_logo = serializers.ImageField(
        required=False,
        allow_null=True
    )
    store_description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )
    
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
    store_logo = serializers.ImageField(read_only=True)

    class Meta:
        model = Store
        fields = ['store_name', 'slug', 'store_description', 'store_logo', 'created_at', 'products']

    def get_products(self, obj):
        from apps.products.serializers import ProductSerializer
        # Only surface active products on the public store page
        active_products = obj.products.filter(is_active=True)
        return ProductSerializer(active_products, many=True).data
