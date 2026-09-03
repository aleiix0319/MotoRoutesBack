from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer, UnreadCountSerializer


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """La campana: mis avisos, mas nuevos primero.

    Solo los mios: el queryset esta filtrado por recipient, asi que la
    notificacion de otro no existe y responde 404, nunca 403.
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    # Igual que en FriendRequestViewSet: esto es para el schema, el
    # queryset real sale de get_queryset().
    queryset = Notification.objects.none()

    def get_queryset(self):
        return (
            Notification.objects
            .filter(recipient=self.request.user)
            .select_related('actor', 'actor__profile')
        )

    @extend_schema(responses={200: UnreadCountSerializer})
    @action(detail=False, methods=['get'], url_path='unread_count')
    def unread_count(self, request):
        """GET notifications/unread_count/ -> el numero de no leidas.

        Es lo que pinta el punto rojo y se pide a menudo: cuenta en SQL, sin
        arrastrar el serializer entero.
        """
        count = self.get_queryset().filter(is_read=False).count()

        return Response({'count': count})

    @extend_schema(request=None, responses={200: NotificationSerializer})
    @action(detail=True, methods=['post'], url_path='read')
    def read(self, request, pk=None):
        """POST notifications/{id}/read/. Idempotente."""
        notification = self.get_object()

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])

        return Response(self.get_serializer(notification).data)

    @extend_schema(request=None, responses={200: UnreadCountSerializer})
    @action(detail=False, methods=['post'], url_path='read_all')
    def read_all(self, request):
        """POST notifications/read_all/ -> el contador que deja detras, 0.

        Lo dispara el cliente al abrir la pantalla. Devuelve el mismo cuerpo
        que unread_count/ para que la campana se apague sin otra llamada.
        """
        self.get_queryset().filter(is_read=False).update(is_read=True)

        return Response({'count': 0})
