from django.shortcuts import render
from rest_framework import viewsets
from .models import Route, RoutePoint
from .serializers import RouteSerializer, RoutePointSerializer


class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.all().order_by('-created_at')
    serializer_class = RouteSerializer

class RoutePointViewSet(viewsets.ModelViewSet):
    queryset = RoutePoint.objects.all().order_by('route', 'order')
    serializer_class = RoutePointSerializer