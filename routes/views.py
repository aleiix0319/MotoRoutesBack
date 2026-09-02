from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly

from .models import Route
from .permissions import IsAuthorOrReadOnly
from .serializers import RouteSerializer


class RouteViewSet(viewsets.ModelViewSet):
    """CRUD de rutas.

    Lectura abierta (las reglas de visibility entran en Fase 2), escritura solo
    autenticado y solo sobre lo propio. El autor sale del token, nunca del body.
    """

    serializer_class = RouteSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]
    queryset = (
        Route.objects
        .select_related('user')
        .prefetch_related('points')
        .order_by('-created_at')
    )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
