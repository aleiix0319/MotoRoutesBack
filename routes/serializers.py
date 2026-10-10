from typing import List, Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import Route, RouteImage, RoutePoint

MIN_POINTS_PER_ROUTE = 2
# El cliente aligera el trazado grabado hasta 1500 como mucho. El limite es
# para que nadie meta cientos de miles de filas en un bulk_create.
MAX_POINTS_PER_ROUTE = 5000

# Duracion en minutos que se acepta en una ruta grabada: hasta 48 h.
MIN_RECORDED_DURATION = 1
MAX_RECORDED_DURATION = 2880


class RouteAuthorSerializer(serializers.Serializer):
    """El autor embebido en la ruta: lo justo para pintar la cabecera."""

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    avatar = serializers.SerializerMethodField()

    def get_avatar(self, obj) -> Optional[str]:
        profile = getattr(obj, 'profile', None)
        return profile.avatar if profile is not None else None


class RoutePointSerializer(serializers.ModelSerializer):
    # order es opcional al escribir: si no viene, se usa la posicion en el array.
    order = serializers.IntegerField(required=False, min_value=0)

    class Meta:
        model = RoutePoint
        fields = [
            'id',
            'latitude',
            'longitude',
            'altitude',
            'order',
        ]
        read_only_fields = ['id']


class RouteSerializer(serializers.ModelSerializer):
    # "user" se mantiene por compatibilidad con el cliente actual; "author" es
    # el campo nuevo. Los dos apuntan al mismo usuario.
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    author = RouteAuthorSerializer(source='user', read_only=True)

    points = RoutePointSerializer(many=True)
    images = serializers.SerializerMethodField()

    is_saved = serializers.SerializerMethodField()
    save_count = serializers.SerializerMethodField()

    # Sin min/max aqui: en una ruta manual la duracion se ignora, y validar el
    # rango a nivel de campo daria 400 por un valor que no se va a usar. El
    # rango se comprueba en validate(), solo cuando cuenta.
    duration = serializers.IntegerField(required=False)

    class Meta:
        model = Route
        fields = [
            'id',
            'user',
            'author',
            'name',
            'description',
            'distance',
            'duration',
            'source',
            'difficulty',
            'visibility',
            'image',
            'images',
            'is_saved',
            'save_count',
            'created_at',
            'updated_at',
            'points',
        ]
        # distance la calcula siempre el servidor desde los puntos: se acepta
        # en el body y se ignora. duration tambien, salvo al crear una ruta
        # grabada (ver validate).
        read_only_fields = ['distance', 'image']

    def get_images(self, obj) -> List[str]:
        urls = [image.url for image in obj.images.all()]

        # Compatibilidad con las rutas antiguas, que tenian una sola "image".
        if not urls and obj.image:
            return [obj.image]

        return urls

    def get_is_saved(self, obj) -> bool:
        # Viene anotado por RouteQuerySet.with_save_state(). Una ruta recien
        # creada todavia no lo trae: nadie ha podido guardarla.
        return bool(getattr(obj, 'is_saved', False))

    def get_save_count(self, obj) -> int:
        return int(getattr(obj, 'save_count', 0))

    def validate_points(self, value):
        if len(value) < MIN_POINTS_PER_ROUTE:
            raise serializers.ValidationError(
                _('Una ruta necesita al menos %(count)d puntos.')
                % {'count': MIN_POINTS_PER_ROUTE}
            )

        if len(value) > MAX_POINTS_PER_ROUTE:
            raise serializers.ValidationError(
                _('Una ruta admite como mucho %(count)d puntos.')
                % {'count': MAX_POINTS_PER_ROUTE}
            )

        given_orders = [
            point['order'] for point in value if point.get('order') is not None
        ]
        if len(set(given_orders)) != len(given_orders):
            raise serializers.ValidationError(
                _('Hay puntos con el mismo "order".')
            )

        return value

    def validate(self, attrs):
        """source y duration solo cuentan al crear una ruta grabada.

        En un PATCH se descartan los dos: el origen no cambia y lo que se
        tardo tampoco. En una ruta manual la duracion se estima a partir de
        la distancia, como siempre.
        """
        if self.instance is not None:
            attrs.pop('source', None)
            attrs.pop('duration', None)
            return attrs

        if attrs.get('source') != Route.SOURCE_RECORDED:
            attrs.pop('duration', None)
            return attrs

        duration = attrs.get('duration')
        if duration is not None and not (
            MIN_RECORDED_DURATION <= duration <= MAX_RECORDED_DURATION
        ):
            raise serializers.ValidationError({
                'duration': [
                    _('La duracion debe estar entre %(min)d y %(max)d '
                      'minutos.')
                    % {
                        'min': MIN_RECORDED_DURATION,
                        'max': MAX_RECORDED_DURATION,
                    }
                ],
            })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        points_data = validated_data.pop('points', [])

        route = Route.objects.create(**validated_data)
        self._replace_points(route, points_data)

        return route

    @transaction.atomic
    def update(self, instance, validated_data):
        points_data = validated_data.pop('points', None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        # En un PATCH sin "points", el trazado se queda como estaba.
        if points_data is not None:
            self._replace_points(instance, points_data)

        return instance

    @staticmethod
    def _replace_points(route, points_data):
        """Reemplaza el trazado entero y recalcula distancia y duracion.

        Todo dentro de la transaccion del create/update: si se corta la
        conexion no quedan rutas a medio crear.
        """
        route.points.all().delete()

        RoutePoint.objects.bulk_create([
            RoutePoint(
                route=route,
                latitude=point['latitude'],
                longitude=point['longitude'],
                altitude=point.get('altitude'),
                order=point.get('order', index),
            )
            for index, point in enumerate(points_data)
        ])

        route.recalculate_from_points()


class RouteMapSerializer(serializers.ModelSerializer):
    """Respuesta ligera de ?near=: lo justo para pintar una chincheta.

    Sin trazado, sin descripcion y sin fotos. Una ruta de 300 puntos pesa aqui
    lo mismo que una de 2.

    Lleva autor y dificultad porque el mapa pinta la chincheta de otro color
    si la ruta es tuya y deja filtrar por dificultad sin abrir la ruta: sin
    esos dos campos el cliente tenia que pedir el listado completo (con
    trazado) solo para clavar chinchetas.
    """

    author = RouteAuthorSerializer(source='user', read_only=True)

    latitude = serializers.DecimalField(
        source='start_latitude',
        max_digits=10,
        decimal_places=7,
        read_only=True,
    )
    longitude = serializers.DecimalField(
        source='start_longitude',
        max_digits=10,
        decimal_places=7,
        read_only=True,
    )

    class Meta:
        model = Route
        fields = [
            'id',
            'name',
            'distance',
            'difficulty',
            'latitude',
            'longitude',
            'author',
        ]
        read_only_fields = fields


class RouteImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouteImage
        fields = ['id', 'url', 'order']
