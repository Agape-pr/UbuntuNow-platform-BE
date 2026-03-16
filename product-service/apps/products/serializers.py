from rest_framework import serializers
from .models import Product, Category, ProductImage

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']
        read_only_fields = ['slug']
class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary']
        read_only_fields = ['id']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    store_name = serializers.CharField(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id',
            'store_id',
            'store_name',
            'category',
            'category_name',
            'name',
            'description',
            'price',
            'stock_quantity',
            'is_active',
            'images',
            'created_at'
        ]
        read_only_fields = ['store_id', 'created_at']



class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Product
        fields = [
            'id',
            'category',
            'name',
            'description',
            'price',
            'stock_quantity',
            'is_active',
            'uploaded_images'
        ]

    def create(self, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])
        product = Product.objects.create(**validated_data)

        for image in uploaded_images:
            ProductImage.objects.create(
                product=product,
                image=image
            )

        return product

    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop('uploaded_images', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        for image in uploaded_images:
            ProductImage.objects.create(
                product=instance,
                image=image
            )

        return instance
