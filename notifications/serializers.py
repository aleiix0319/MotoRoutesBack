from rest_framework import serializers

from users.serializers import UserBriefSerializer

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """NotificationDto.

    `friendship_id` es lo que permite aceptar desde la propia notificacion sin
    una segunda llamada para averiguar de que solicitud hablamos. Es null
    cuando el aviso no va de amistad o cuando la fila ya no existe.
    """

    actor = UserBriefSerializer(read_only=True)
    friendship_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Notification
        fields = [
            'id',
            'type',
            'actor',
            'friendship_id',
            'is_read',
            'created_at',
        ]
        read_only_fields = fields


class UnreadCountSerializer(serializers.Serializer):
    """Cuerpo de notifications/unread_count/. Solo documentacion."""

    count = serializers.IntegerField()
