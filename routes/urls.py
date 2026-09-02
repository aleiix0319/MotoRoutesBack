from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RouteViewSet

# route-points/ retirado: los puntos viajan anidados dentro de la ruta, no hay
# razon para exponerlos como CRUD suelto.
router = DefaultRouter()
router.register(r'routes', RouteViewSet, basename='routes')

urlpatterns = [
    path('', include(router.urls)),
]
