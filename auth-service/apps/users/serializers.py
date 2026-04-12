from rest_framework import serializers
from django.contrib.auth import get_user_model
import requests
import os
import logging
logger = logging.getLogger(__name__)

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    account_type = serializers.ChoiceField(
        choices=[('buyer', 'Buyer'), ('seller', 'Seller')],
        write_only=True
    )
    password = serializers.CharField(write_only=True)
    store = serializers.DictField(required=False, allow_null=True)


    def validate(self, attrs):
        import json
        account_type = attrs.get('account_type')
        store_data = attrs.get('store')

        # If store_data is a string (because of multipart/form-data), parse it
        if isinstance(store_data, str):
            try:
                store_data = json.loads(store_data)
                attrs['store'] = store_data
            except json.JSONDecodeError:
                raise serializers.ValidationError({
                    "store": "Invalid JSON format for store data."
                })

        # Seller must provide store data with store_name
        if account_type == 'seller':
            if not store_data:
                raise serializers.ValidationError({
                    "store": "Store data is required for sellers."
                })
            if not store_data.get('store_name') or not store_data.get('store_name', '').strip():
                raise serializers.ValidationError({
                    "store": {"store_name": "Store name is required for sellers."}
                })
            # Normalize empty string to None for optional fields
            if store_data.get('store_description') == '':
                store_data['store_description'] = None

        # Buyer must NOT provide store data
        if account_type == 'buyer' and store_data:
            raise serializers.ValidationError({
                "store": "Buyers are not allowed to create a store."
            })

        return attrs


    class Meta:
        model = User
        fields = ['email', 'password', 'account_type', 'phone_number', 'store']

    def create(self, validated_data):
        store_data = validated_data.pop('store', None)
        password = validated_data.pop('password')
        account_type = validated_data.pop('account_type')

        role = (
            User.Role.SELLER
            if account_type == 'seller'
            else User.Role.BUYER
        )

        user = User.objects.create_user(
            email=validated_data['email'],
            password=password,
            phone_number=validated_data.get('phone_number'),
            role=role,
            username=validated_data['email'],
            is_active=False,
        )

        if role == User.Role.SELLER and store_data:
            try:
                store_data['user_id'] = user.id
                store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')
                res = requests.post(f"{store_url}/api/v1/users/internal/stores/", json=store_data, timeout=5)
                if res.status_code not in [200, 201]:
                    logger.error(f"Failed to create store: {res.text}")
            except Exception as e:
                logger.error(f"Store service unreachable: {e}")
        return user
class UserDetailSerializer(serializers.ModelSerializer):
    store = serializers.SerializerMethodField()
    
    
    def get_store(self, obj):
        if obj.role == 'seller':
            try:
                store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')
                res = requests.get(f"{store_url}/api/v1/users/internal/stores/{obj.id}/", timeout=2)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                pass
        return None

    class Meta:
        model = User
        fields = ['id', 'email', 'role', 'phone_number', 'store', 'is_superuser', 'admin_permissions']

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims for RBAC
        token['role'] = user.role
        token['is_superuser'] = user.is_superuser
        token['admin_permissions'] = user.admin_permissions
        
        # Inject store_id into JWT for seller stateless auth downstream
        if user.role == 'seller':
            try:
                store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')
                # Try fetching store via internal network
                res = requests.get(f"{store_url}/api/v1/users/internal/stores/{user.id}/", timeout=2)
                if res.status_code == 200:
                    token['store_id'] = res.json().get('id')
            except Exception as e:
                logger.error(f"Failed to append store_id to JWT: {e}")
                
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Add user info to the response
        user_serializer = UserDetailSerializer(self.user)
        data['user'] = user_serializer.data
        
        return data


class AdminUserSerializer(serializers.ModelSerializer):
    """Full user profile for admin panel — includes store data for sellers."""
    store = serializers.SerializerMethodField()

    def get_store(self, obj):
        if obj.role == 'seller':
            try:
                store_url = os.environ.get('STORE_SERVICE_URL', 'http://store-service:8002')
                res = requests.get(
                    f"{store_url}/api/v1/users/internal/stores/{obj.id}/",
                    timeout=3
                )
                if res.status_code == 200:
                    return res.json()
            except Exception:
                pass
        return None

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'role', 'phone_number',
            'is_active', 'is_staff', 'is_superuser', 'admin_permissions',
            'date_joined', 'last_login', 'store'
        ]

class AdminUserCreateSerializer(serializers.ModelSerializer):
    """Used strictly by Super Admins to create sub-admins or regular users manually."""
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['email', 'password', 'role', 'admin_permissions', 'phone_number']

    def create(self, validated_data):
        password = validated_data.pop('password')
        role = validated_data.pop('role', User.Role.BUYER)
        admin_permissions = validated_data.pop('admin_permissions', [])
        
        # When creating a user via Admin, they are verified immediately
        user = User.objects.create_user(
            email=validated_data['email'],
            password=password,
            username=validated_data['email'],
            role=role,
            is_active=True,
            admin_permissions=admin_permissions,
            **validated_data
        )

        # Grant Django admin access automatically if role is admin
        if role == 'admin':
            user.is_staff = True
            user.save()

        return user
