import re

from django.contrib.auth import get_user_model

User = get_user_model()

MAX_USERNAME_LENGTH = 150


def generate_unique_username(email, fallback='rider'):
    """Deriva un username libre a partir del email.

    Se usa en el alta por Firebase, donde no hay formulario que pida username.
    El usuario puede cambiarlo despues desde su perfil.
    """
    local_part = (email or '').split('@')[0]
    base = re.sub(r'[^A-Za-z0-9_.-]', '', local_part).strip('._-').lower()

    if not base:
        base = fallback

    base = base[:MAX_USERNAME_LENGTH - 6]

    if not User.objects.filter(username=base).exists():
        return base

    for suffix in range(1, 10000):
        candidate = f"{base}{suffix}"
        if not User.objects.filter(username=candidate).exists():
            return candidate

    raise RuntimeError('No se pudo generar un username libre')


def following_ids(user):
    """IDs de la gente a la que `user` sigue. Devuelve un queryset perezoso."""
    from .models import Follow

    if not getattr(user, 'is_authenticated', False):
        return Follow.objects.none().values('following_id')

    return Follow.objects.filter(follower=user).values('following_id')


def mutual_follow_ids(user):
    """IDs de la gente con la que `user` se sigue mutuamente ("amigos").

    Una sola subconsulta: los que yo sigo Y que ademas me siguen.
    """
    from .models import Follow

    if not getattr(user, 'is_authenticated', False):
        return Follow.objects.none().values('following_id')

    followers_of_user = Follow.objects.filter(following=user).values(
        'follower_id'
    )

    return (
        Follow.objects
        .filter(follower=user, following_id__in=followers_of_user)
        .values('following_id')
    )
