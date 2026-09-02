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
