from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from favorites.models import Favorite
from users.services import following_ids

from .geo import bounding_box, haversine_km
from .models import Route
from .permissions import IsAuthorOrReadOnly
from .serializers import RouteMapSerializer, RouteSerializer

DEFAULT_RADIUS_KM = 25.0
MAX_RADIUS_KM = 500.0

FEED_FOR_YOU = 'for_you'
FEED_FOLLOWING = 'following'
FEEDS = (FEED_FOR_YOU, FEED_FOLLOWING)


class RouteViewSet(viewsets.ModelViewSet):
    """CRUD de rutas, feeds y guardados.

    La visibilidad no se filtra nunca en el cliente: todo lo que sale de aqui
    ha pasado antes por Route.objects.visible_to(request.user).
    """

    serializer_class = RouteSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly]

    def get_serializer_class(self):
        if self.action == 'list' and 'near' in self.request.query_params:
            return RouteMapSerializer
        return RouteSerializer

    def get_queryset(self):
        user = self.request.user

        queryset = (
            Route.objects
            .visible_to(user)
            .with_save_state(user)
            .select_related('user', 'user__profile')
            .for_feed()
        )

        # El mapa no necesita el trazado ni las fotos: no los traemos.
        if self.action == 'list' and 'near' in self.request.query_params:
            return queryset

        return queryset.prefetch_related('points', 'images')

    def filter_queryset(self, queryset):
        # get_object() tambien pasa por aqui; los filtros son solo de listado.
        if self.action != 'list':
            return queryset

        params = self.request.query_params

        queryset = self._filter_by_feed(queryset, params.get('feed'))
        queryset = self._filter_by_author(queryset, params.get('author'))

        if 'near' in params:
            return self._filter_by_proximity(queryset, params)

        return queryset

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # Filtros de listado

    def _filter_by_feed(self, queryset, feed):
        if feed is None:
            return queryset

        if feed not in FEEDS:
            raise ValidationError({
                'feed': [f"Valores validos: {', '.join(FEEDS)}."]
            })

        if feed == FEED_FOR_YOU:
            # Publicas y solo publicas, aunque haya sesion: es el feed de
            # descubrimiento, no el de tus contactos.
            return queryset.filter(visibility=Route.VISIBILITY_PUBLIC)

        self._require_authentication()

        # visible_to() ya ha recortado: de la gente que sigo veo sus publicas y,
        # si nos seguimos mutuamente, tambien sus "friends".
        return queryset.filter(user_id__in=following_ids(self.request.user))

    def _filter_by_author(self, queryset, author):
        if author is None:
            return queryset

        if author == 'me':
            self._require_authentication()
            return queryset.filter(user=self.request.user)

        try:
            author_id = int(author)
        except (TypeError, ValueError):
            raise ValidationError({
                'author': ['Debe ser un id de usuario o "me".']
            })

        return queryset.filter(user_id=author_id)

    def _filter_by_proximity(self, queryset, params):
        latitude, longitude = self._parse_near(params.get('near'))
        radius_km = self._parse_radius(params.get('radius_km'))

        min_lat, max_lat, min_lon, max_lon = bounding_box(
            latitude, longitude, radius_km
        )

        # La caja recorta en SQL con el indice; el haversine solo se ejecuta
        # sobre lo poco que sobrevive.
        candidates = queryset.in_bounding_box(
            min_lat, max_lat, min_lon, max_lon
        )

        return [
            route for route in candidates
            if haversine_km(
                latitude,
                longitude,
                route.start_latitude,
                route.start_longitude,
            ) <= radius_km
        ]

    @staticmethod
    def _parse_near(raw):
        parts = (raw or '').split(',')

        if len(parts) != 2:
            raise ValidationError({
                'near': ['Formato esperado: near=latitud,longitud.']
            })

        try:
            latitude = float(parts[0])
            longitude = float(parts[1])
        except ValueError:
            raise ValidationError({
                'near': ['Latitud y longitud deben ser numeros.']
            })

        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValidationError({
                'near': ['Latitud entre -90 y 90, longitud entre -180 y 180.']
            })

        return latitude, longitude

    @staticmethod
    def _parse_radius(raw):
        if raw is None:
            return DEFAULT_RADIUS_KM

        try:
            radius_km = float(raw)
        except ValueError:
            raise ValidationError({'radius_km': ['Debe ser un numero.']})

        if not 0 < radius_km <= MAX_RADIUS_KM:
            raise ValidationError({
                'radius_km': [f'Debe estar entre 0 y {MAX_RADIUS_KM:.0f}.']
            })

        return radius_km

    def _require_authentication(self):
        if not self.request.user.is_authenticated:
            raise NotAuthenticated()

    # Acciones

    @extend_schema(
        responses={200: RouteSerializer(many=True)},
        parameters=[
            OpenApiParameter(
                'saved',
                description='Rutas que ha guardado quien hace la peticion.',
            ),
        ],
    )
    @action(
        detail=False,
        methods=['get'],
        permission_classes=[IsAuthenticated],
    )
    def saved(self, request):
        """GET routes/saved/ -> las rutas que he guardado."""
        queryset = self.get_queryset().filter(favorites__user=request.user)

        return Response(self.get_serializer(queryset, many=True).data)

    @extend_schema(
        request=None,
        responses={200: {
            'type': 'object',
            'properties': {
                'is_saved': {'type': 'boolean'},
                'save_count': {'type': 'integer'},
            },
        }},
    )
    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[IsAuthenticated],
    )
    def save(self, request, pk=None):
        """POST / DELETE routes/{id}/save/. Idempotentes las dos."""
        route = self.get_object()

        if request.method == 'POST':
            Favorite.objects.get_or_create(user=request.user, route=route)
            is_saved = True
        else:
            Favorite.objects.filter(user=request.user, route=route).delete()
            is_saved = False

        return Response(
            {
                'is_saved': is_saved,
                'save_count': route.favorites.count(),
            },
            status=status.HTTP_200_OK,
        )
