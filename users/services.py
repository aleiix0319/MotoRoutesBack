import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, When
from django.utils import timezone

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


def friend_ids(user):
    """IDs de las personas con las que `user` tiene una amistad aceptada.

    La amistad es simetrica y se guarda en una sola fila, asi que hay que
    mirar los dos extremos: si yo soy el from_user el amigo es el to_user y al
    reves. Devuelve un queryset perezoso de una sola columna, pensado para
    meterlo en un `user_id__in=`: visible_to() lo resuelve como subconsulta,
    sin una segunda ida a la base de datos.
    """
    from .models import Friendship

    if not getattr(user, 'is_authenticated', False):
        return Friendship.objects.none().values('to_user_id')

    return (
        Friendship.objects
        .filter(status=Friendship.STATUS_ACCEPTED)
        .filter(Q(from_user=user) | Q(to_user=user))
        .annotate(
            friend_id=Case(
                When(from_user=user, then=F('to_user_id')),
                default=F('from_user_id'),
                output_field=IntegerField(),
            )
        )
        .values('friend_id')
    )


def friends_of(user):
    """Queryset de usuarios amigos de `user`, ordenado por username."""
    return (
        User.objects
        .filter(is_active=True, id__in=friend_ids(user))
        .select_related('profile')
        .order_by('username')
    )


def friendship_between(user, other):
    """La fila que une a dos usuarios, mirada en los dos sentidos. O None."""
    from .models import Friendship

    return (
        Friendship.objects
        .filter(
            Q(from_user=user, to_user=other)
            | Q(from_user=other, to_user=user)
        )
        .select_related('from_user', 'to_user')
        .first()
    )


@transaction.atomic
def create_friend_request(from_user, to_user):
    """Pide amistad. Devuelve (friendship, created).

    created=True solo cuando nace una fila nueva (201). Todo lo demas responde
    200 con la fila que ya habia, porque repetir una solicitud no es un error:

      - ya la habia enviado yo        -> la misma fila, sigue pending
      - ya somos amigos              -> la misma fila, accepted
      - el otro me la habia enviado  -> se acepta en el acto y salimos amigos
    """
    from .models import Friendship

    existing = friendship_between(from_user, to_user)

    if existing is not None:
        if existing.status == Friendship.STATUS_ACCEPTED:
            return existing, False

        if existing.from_user_id == from_user.id:
            return existing, False

        # Solicitudes cruzadas: el otro ya me la habia pedido. Crear una
        # segunda fila dejaria dos solicitudes vivas por el mismo par, asi que
        # cerramos la suya.
        return accept_friend_request(existing), False

    friendship = Friendship.objects.create(
        from_user=from_user,
        to_user=to_user,
    )

    from notifications.services import notify_friend_request

    notify_friend_request(friendship)

    return friendship, True


@transaction.atomic
def accept_friend_request(friendship):
    """Acepta una solicitud pendiente. Idempotente: aceptar dos veces vale."""
    from .models import Friendship

    if friendship.status == Friendship.STATUS_ACCEPTED:
        return friendship

    friendship.status = Friendship.STATUS_ACCEPTED
    friendship.responded_at = timezone.now()
    friendship.save(update_fields=['status', 'responded_at'])

    from notifications.services import (
        drop_friend_request_notification,
        notify_friend_request_accepted,
    )

    drop_friend_request_notification(friendship)
    notify_friend_request_accepted(friendship)

    return friendship


@transaction.atomic
def delete_friendship(friendship):
    """Rechaza, cancela o deshace, que en esta tabla es lo mismo: borrar.

    No se guarda un estado 'rejected': quien pidio vuelve a ver el boton de
    enviar solicitud y no se entera de que le han dicho que no. Ademas evita
    acumular filas muertas que habria que ignorar en cada consulta.
    """
    from notifications.services import drop_friend_request_notification

    drop_friend_request_notification(friendship)
    friendship.delete()


def with_profile_stats(queryset, viewer):
    """Anota en un queryset de usuarios todo lo que pinta el perfil.

    route_count, friend_count y el estado de la relacion con `viewer` en
    subconsultas, para que una lista de amigos no dispare tres consultas por
    fila. El serializer las lee si estan y las calcula al vuelo si no.
    """
    from django.db.models import Count, IntegerField, OuterRef, Subquery
    from django.db.models.functions import Coalesce

    from routes.models import Route

    from .models import Friendship

    visible_routes = (
        Route.objects
        .visible_to(viewer)
        .filter(user=OuterRef('pk'))
        .order_by()
        .values('user')
        .annotate(total=Count('pk'))
        .values('total')
    )

    accepted = Friendship.objects.filter(status=Friendship.STATUS_ACCEPTED)

    # La amistad vive en una sola fila, asi que hay que contar los dos
    # extremos. Dos subconsultas agrupadas por una columna real en vez de una
    # con OR: el OR no se puede agrupar y obligaria a trucos de constante.
    sent = (
        accepted
        .filter(from_user=OuterRef('pk'))
        .order_by()
        .values('from_user')
        .annotate(total=Count('pk'))
        .values('total')
    )
    received = (
        accepted
        .filter(to_user=OuterRef('pk'))
        .order_by()
        .values('to_user')
        .annotate(total=Count('pk'))
        .values('total')
    )

    queryset = queryset.annotate(
        route_count=Coalesce(
            Subquery(visible_routes, output_field=IntegerField()), 0
        ),
        friend_count=(
            Coalesce(Subquery(sent, output_field=IntegerField()), 0)
            + Coalesce(Subquery(received, output_field=IntegerField()), 0)
        ),
    )

    if not getattr(viewer, 'is_authenticated', False):
        return queryset

    relation = Friendship.objects.filter(
        Q(from_user=OuterRef('pk'), to_user=viewer)
        | Q(from_user=viewer, to_user=OuterRef('pk'))
    )

    return queryset.annotate(
        relation_id=Subquery(relation.values('id')[:1]),
        relation_status=Subquery(relation.values('status')[:1]),
        relation_from_user_id=Subquery(relation.values('from_user_id')[:1]),
    )
