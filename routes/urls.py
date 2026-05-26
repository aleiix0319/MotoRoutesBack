from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RouteViewSet, RoutePointViewSet

router = DefaultRouter()
router.register(r'routes', RouteViewSet, basename='routes')
router.register(r'route-points', RoutePointViewSet, basename='route-points')

urlpatterns = [
    path('', include(router.urls)),
]