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


class Follow(models.Model):
    """Seguimiento unidireccional, estilo Instagram.

    "Amigos" no es una tabla: son dos filas de esta, una en cada sentido. Lo
    resuelve users.services.mutual_follow_ids(), que es lo que consulta la
    visibilidad "friends" de las rutas.
    """

    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='following_set',
    )

    following = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='follower_set',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['follower', 'following'],
                name='unique_follow',
            ),
            models.CheckConstraint(
                check=~Q(follower=models.F('following')),
                name='no_self_follow',
            ),
        ]
        indexes = [
            models.Index(fields=['follower', 'following']),
            models.Index(fields=['following', 'follower']),
        ]

    def __str__(self):
        return f"{self.follower.username} -> {self.following.username}"
