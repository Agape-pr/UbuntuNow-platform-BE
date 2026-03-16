from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .models import Store
from .serializers import StoreSerializer, PublicStoreSerializer
from rest_framework.permissions import AllowAny

class InternalStoreCreateView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = StoreSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class InternalStoreRetrieveView(APIView):
    permission_classes = [AllowAny]
    def get(self, request, user_id):
        try:
            store = Store.objects.get(user_id=user_id)
            return Response(StoreSerializer(store).data)
        except Store.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)

class PublicStoreView(generics.RetrieveAPIView):
    queryset = Store.objects.all()
    serializer_class = PublicStoreSerializer
    lookup_field = 'slug'
    permission_classes = [AllowAny]
