from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Friendship
from .serializers import (
    FriendRequestCreateSerializer,
    FriendshipSerializer,
    UserSerializer,
)
from .services import (
    accept_friend_request,
    create_friend_request,
    delete_friendship,
    friends_of,
    with_profile_stats,
)

User = get_user_model()

DIRECTION_INCOMING = 'incoming'
DIRECTION_OUTGOING = 'outgoing'
DIRECTIONS = (DIRECTION_INCOMING, DIRECTION_OUTGOING)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """GET users/ y GET users/{id}/.

    Solo lectura: las altas van por authentication (register / firebase) y la
    edicion del propio perfil llegara en PATCH users/me/ (Fase 3).

    El queryset viene anotado con los contadores y el estado de la amistad,
    que dependen de quien pregunta: el mismo usuario se serializa distinto
    segun quien abra su perfil.
    """

    serializer_class = UserSerializer

    def get_queryset(self):
        base = (
            User.objects
            .filter(is_active=True)
            .select_related('profile')
            .order_by('id')
        )

        return with_profile_stats(base, self.request.user)


class FriendRequestViewSet(mixins.CreateModelMixin,
                           mixins.ListModelMixin,
                           mixins.DestroyModelMixin,
                           viewsets.GenericViewSet):
    """Solicitudes de amistad.

    El queryset son siempre mis filas, en cualquiera de los dos extremos: lo
    que no es mio no existe y responde 404, nunca 403.
    """

    serializer_class = FriendshipSerializer
    permission_classes = [IsAuthenticated]
    # Solo para que drf-spectacular sepa de que modelo habla: el queryset
    # de verdad lo arma get_queryset() con el usuario de la peticion.
    queryset = Friendship.objects.none()

    def get_queryset(self):
        user = self.request.user

        return (
            Friendship.objects
            .filter(Q(from_user=user) | Q(to_user=user))
            .select_related(
                'from_user',
                'from_user__profile',
                'to_user',
                'to_user__profile',
            )
            .order_by('-created_at', '-id')
        )

    def filter_queryset(self, queryset):
        # get_object() tambien pasa por aqui: el filtro es solo de listado.
        if self.action != 'list':
            return queryset

        direction = self.request.query_params.get(
            'direction', DIRECTION_INCOMING
        )

        if direction not in DIRECTIONS:
            raise ValidationError({
                'direction': ['Valores validos: incoming, outgoing.']
            })

        queryset = queryset.filter(status=Friendship.STATUS_PENDING)

        if direction == DIRECTION_INCOMING:
            return queryset.filter(to_user=self.request.user)

        return queryset.filter(from_user=self.request.user)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'direction',
                enum=list(DIRECTIONS),
                description=(
                    'incoming (las que me han enviado, por defecto) u '
                    'outgoing. Solo las pendientes.'
                ),
            ),
        ],
        responses={200: FriendshipSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=FriendRequestCreateSerializer,
        responses={201: FriendshipSerializer, 200: FriendshipSerializer},
    )
    def create(self, request, *args, **kwargs):
        """POST friends/requests/ con el id del destinatario.

        201 solo cuando nace una solicitud nueva. 200 si ya existia o si
        cerraba una inversa pendiente, en cuyo caso ya sois amigos: repetir
        una solicitud no es un error.
        """
        serializer = FriendRequestCreateSerializer(
            data=request.data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)

        friendship, created = create_friend_request(
            request.user,
            serializer.validated_data['to_user'],
        )

        return Response(
            FriendshipSerializer(friendship).data,
            status=(
                status.HTTP_201_CREATED if created else status.HTTP_200_OK
            ),
        )

    @extend_schema(request=None, responses={200: FriendshipSerializer})
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """POST friends/requests/{id}/accept/. Solo el destinatario."""
        friendship = get_object_or_404(
            self.get_queryset().filter(to_user=request.user),
            pk=pk,
        )

        accept_friend_request(friendship)

        return Response(FriendshipSerializer(friendship).data)

    def perform_destroy(self, instance):
        """DELETE friends/requests/{id}/: rechazar o cancelar, segun quien sea.

        Es la misma fila y el mismo permiso, asi que es el mismo endpoint.
        """
        delete_friendship(instance)


@extend_schema(
    parameters=[
        OpenApiParameter(
            'user',
            description='Amigos de ese usuario. Sin el, los mios.',
        ),
    ],
    responses={200: UserSerializer(many=True)},
)
class FriendListView(ListAPIView):
    """GET friends/?user={id} -> lista de UserDto."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        owner = self.request.user
        raw = self.request.query_params.get('user')

        if raw is not None:
            try:
                owner_id = int(raw)
            except (TypeError, ValueError):
                raise ValidationError({
                    'user': ['Debe ser un id de usuario.']
                })

            owner = get_object_or_404(User, pk=owner_id, is_active=True)

        return with_profile_stats(friends_of(owner), self.request.user)


class FriendDetailView(APIView):
    """DELETE friends/{user_id}/ -> deshacer amistad.

    Por id de usuario y no de fila: el cliente esta en un perfil y no tiene
    por que saber quien pidio a quien. Idempotente: si no erais amigos
    tampoco es un error, la peticion ya deja el mundo como pedia.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, user_id):
        friendship = (
            Friendship.objects
            .filter(status=Friendship.STATUS_ACCEPTED)
            .filter(
                Q(from_user=request.user, to_user_id=user_id)
                | Q(from_user_id=user_id, to_user=request.user)
            )
            .first()
        )

        if friendship is not None:
            delete_friendship(friendship)

        return Response(status=status.HTTP_204_NO_CONTENT)
