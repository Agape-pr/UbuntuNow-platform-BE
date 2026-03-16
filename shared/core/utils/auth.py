from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from django.contrib.auth.models import AnonymousUser
from types import SimpleNamespace

class StatelessUser:
    def __init__(self, token_payload):
        # We assume the token provides user_id and role
        self.id = token_payload.get('user_id')
        self.pk = self.id
        self.role = token_payload.get('role', 'buyer')
        self.is_authenticated = True
        self.is_active = True
        self.store = SimpleNamespace(id=token_payload.get('store_id')) if token_payload.get('store_id') else None

    def getattr(self, item):
        return None

    def is_seller(self):
        return self.role == 'seller'

    def is_buyer(self):
        return self.role == 'buyer'

    @property
    def is_anonymous(self):
        return False


class JWTStatelessAuthentication(JWTAuthentication):
    """
    A custom authentication class for microservices that do not have 
    the User table in their local database. It parses the JWT and 
    returns a mock user object.
    """
    def get_user(self, validated_token):
        user_id = validated_token.get('user_id')
        if not user_id:
            raise AuthenticationFailed('Token contained no recognizable user identification')
        return StatelessUser(validated_token)
