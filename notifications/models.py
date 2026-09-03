from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Aviso para la campana del cliente.

    Tabla propia y no un calculo sobre Friendship: asi la campana puede llevar
    contador de no leidas y caben avisos que no son de amistad sin rehacerla.

    `friendship` es lo que permite aceptar desde la propia notificacion sin
    una segunda llamada para averiguar de que solicitud hablamos. Queda a null
    si la fila desaparece (deshacer amistad), porque el aviso de
    'friend_request_accepted' es informativo y sobrevive a la amistad.
    """

    TYPE_FRIEND_REQUEST = 'friend_request'
    TYPE_FRIEND_REQUEST_ACCEPTED = 'friend_request_accepted'

    TYPE_CHOICES = [
        (TYPE_FRIEND_REQUEST, 'Friend request'),
        (TYPE_FRIEND_REQUEST_ACCEPTED, 'Friend request accepted'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )

    # Quien provoca el aviso. Si se borra su cuenta, el aviso deja de tener
    # sentido: se va con el.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications_caused',
    )

    type = models.CharField(max_length=40, choices=TYPE_CHOICES)

    friendship = models.ForeignKey(
        'users.Friendship',
        on_delete=models.SET_NULL,
        related_name='notifications',
        blank=True,
        null=True,
    )

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.type} -> {self.recipient.username}"
