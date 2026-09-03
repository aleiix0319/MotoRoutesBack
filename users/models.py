from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver


class Profile(models.Model):
    """Datos de MotoRoutes que cuelgan de un auth.User.

    El usuario canonico de la app es django.contrib.auth.User. Este modelo
    guarda solo lo que auth.User no tiene, y el serializer lo aplana a la raiz
    del JSON: el cliente ve "avatar" y "bio" al mismo nivel que "username".
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )

    firebase_uid = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        null=True,
    )

    avatar = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    """Todo usuario tiene Profile desde el momento en que existe.

    Asi el serializer nunca se encuentra un user sin profile, venga de donde
    venga el alta (Firebase, registro, createsuperuser o el admin).
    """
    if created:
        Profile.objects.get_or_create(user=instance)


class Friendship(models.Model):
    """Amistad entre dos personas, con solicitud explicita.

    La fila la crea quien pide (from_user). Mientras esta en 'pending' no
    concede nada; al aceptarla pasa a 'accepted' y es entonces cuando los dos
    se ven las rutas de visibilidad 'friends'. La relacion es simetrica: da
    igual quien pidiera, se consulta en los dos sentidos, y por eso el par
    (A, B) y el par (B, A) no pueden coexistir. Eso no lo puede garantizar la
    restriccion unica, que es sobre el par ordenado: lo cierra
    users.services.create_friend_request().
    """

    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
    ]

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='friend_requests_sent',
    )

    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='friend_requests_received',
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['from_user', 'to_user'],
                name='unique_friendship',
            ),
            models.CheckConstraint(
                check=~Q(from_user=models.F('to_user')),
                name='no_self_friendship',
            ),
        ]
        indexes = [
            models.Index(fields=['to_user', 'status']),
            models.Index(fields=['from_user', 'status']),
        ]

    def __str__(self):
        return f"{self.from_user.username} -> {self.to_user.username} ({self.status})"

    def other_user(self, user):
        """El otro extremo de la amistad visto desde `user`."""
        return self.to_user if self.from_user_id == user.id else self.from_user
