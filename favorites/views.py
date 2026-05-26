from django.shortcuts import render
from rest_framework import viewsets
from .models import Favorite
from .serializers import FavoriteSerializer


class FavoriteViewSet(viewsets.ModelViewSet):
    queryset = Favorite.objects.all().order_by('-created_at')
    serializer_class = FavoriteSerializer
