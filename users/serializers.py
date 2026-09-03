from typing import Optional

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from .models import Friendship

User = get_user_model()

STATUS_NONE = 'none'
STATUS_PENDING_SENT = 'pending_sent'
STATUS_PENDING_RECEIVED = 'pending_received'
STATUS_FRIENDS = 'friends'


def _avatar_of(user) -> Optional[str]:
    profile = getattr(user, 'profile', None)
    return profile.avatar if profile is not None else None


class UserBriefSerializer(serializers.Serializer):
    """Lo justo para pintar una fila: solicitudes, notificaciones y autores."""

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    avatar = serializers.SerializerMethodField()

    def get_avatar(self, obj) -> Optional[str]:
        return _avatar_of(obj)


class UserSerializer(serializers.ModelSerializer):
    """UserDto publico: lo que ve cualquiera que abra un perfil ajeno.

    Los campos del Profile 1-1 se aplanan a la raiz: el cliente espera
    "avatar" y "bio" al mismo nivel que "username", no anidados.

    Sin email. Un perfil ajeno es navegable desde la app, y el correo de otra
    persona no es dato publico: viaja solo en auth/me/, con UserMeSerializer.

    Los contadores y el estado de la relacion dependen de quien pregunta, asi
    que se leen de las anotaciones que pone UserViewSet.get_queryset(). Si el
    serializer se usa suelto (una sola instancia, sin anotar) se calculan al
    vuelo: es una consulta mas, pero no un N+1, porque ahi solo hay un objeto.
    """

    avatar = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    route_count = serializers.SerializerMethodField()
    friend_count = serializers.SerializerMethodField()
    is_me = serializers.SerializerMethodField()
    friendship_status = serializers.SerializerMethodField()
    friendship_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'avatar',
            'bio',
            'route_count',
            'friend_count',
            'is_me',
            'friendship_status',
            'friendship_id',
        ]
        read_only_fields = fields

    # Perfil

    def get_avatar(self, obj) -> Optional[str]:
        return _avatar_of(obj)

    def get_bio(self, obj) -> str:
        profile = getattr(obj, 'profile', None)
        return profile.bio if profile is not None else ''

    # Contadores

    def get_route_count(self, obj) -> int:
        annotated = getattr(obj, 'route_count', None)
        if annotated is not None:
            return int(annotated)

        from routes.models import Route

        return (
            Route.objects
            .visible_to(self._viewer())
            .authored_by(obj)
            .count()
        )

    def get_friend_count(self, obj) -> int:
        annotated = getattr(obj, 'friend_count', None)
        if annotated is not None:
            return int(annotated)

        return (
            Friendship.objects
            .filter(status=Friendship.STATUS_ACCEPTED)
            .filter(Q(from_user=obj) | Q(to_user=obj))
            .count()
        )

    # Relacion con quien pregunta

    def get_is_me(self, obj) -> bool:
        viewer = self._viewer()
        return bool(viewer and viewer.is_authenticated and viewer.id == obj.id)

    def get_friendship_status(self, obj) -> str:
        status, from_user_id = self._relation(obj)

        if status is None:
            return STATUS_NONE

        if status == Friendship.STATUS_ACCEPTED:
            return STATUS_FRIENDS

        viewer = self._viewer()
        if from_user_id == viewer.id:
            return STATUS_PENDING_SENT

        return STATUS_PENDING_RECEIVED

    def get_friendship_id(self, obj) -> Optional[int]:
        friendship_id = self._relation(obj, field='id')[0]
        return friendship_id

    # Interno

    def _viewer(self):
        """Quien hace la peticion. auth/me/ lo pasa explicito en el contexto."""
        viewer = self.context.get('viewer')
        if viewer is not None:
            return viewer

        request = self.context.get('request')
        return getattr(request, 'user', None)

    def _relation(self, obj, field='status'):
        """(valor, from_user_id) de la fila que me une a `obj`, o (None, None).

        Sale de las anotaciones de UserViewSet cuando estan; si no, de una
        consulta suelta. Se cachea en la instancia porque tres campos del
        serializer preguntan por lo mismo.
        """
        viewer = self._viewer()

        if (
            viewer is None
            or not viewer.is_authenticated
            or viewer.id == obj.id
        ):
            return None, None

        if hasattr(obj, 'relation_status'):
            values = {
                'id': getattr(obj, 'relation_id', None),
                'status': obj.relation_status,
            }
            return values[field], getattr(obj, 'relation_from_user_id', None)

        cached = getattr(obj, '_relation_cache', 'missing')
        if cached == 'missing':
            from .services import friendship_between

            cached = friendship_between(viewer, obj)
            obj._relation_cache = cached

        if cached is None:
            return None, None

        value = cached.id if field == 'id' else cached.status
        return value, cached.from_user_id


class UserMeSerializer(UserSerializer):
    """El propio usuario: igual que el publico, mas el email."""

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['email']
        read_only_fields = fields


class FriendshipSerializer(serializers.ModelSerializer):
    """FriendshipDto: la solicitud tal y como la pinta el cliente."""

    from_user = UserBriefSerializer(read_only=True)
    to_user = UserBriefSerializer(read_only=True)

    class Meta:
        model = Friendship
        fields = ['id', 'from_user', 'to_user', 'status', 'created_at']
        read_only_fields = fields


class FriendRequestCreateSerializer(serializers.Serializer):
    """Cuerpo de POST friends/requests/: {"to_user": 7}."""

    to_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
    )

    def validate_to_user(self, value):
        if value == self.context['request'].user:
            raise serializers.ValidationError(
                'No puedes enviarte una solicitud a ti mismo.'
            )
        return value
