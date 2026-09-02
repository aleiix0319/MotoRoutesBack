from django.db import transaction
from rest_framework import serializers

from .models import Route, RouteImage, RoutePoint

MIN_POINTS_PER_ROUTE = 2


class RouteAuthorSerializer(serializers.Serializer):
    """El autor embebido en la ruta: lo justo para pintar la cabecera."""

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    avatar = serializers.SerializerMethodField()

    def get_avatar(self, obj) -> str | None:
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
        # distance y duration las calcula el servidor desde los puntos. Se
        # aceptan en el body y se ignoran, para no obligar a desplegar cliente
        # y servidor el mismo dia.
        read_only_fields = ['distance', 'duration', 'image']

    def get_images(self, obj) -> list:
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
                f'Una ruta necesita al menos {MIN_POINTS_PER_ROUTE} puntos.'
            )

        given_orders = [
            point['order'] for point in value if point.get('order') is not None
        ]
        if len(set(given_orders)) != len(given_orders):
            raise serializers.ValidationError(
                'Hay puntos con el mismo "order".'
            )

        return value

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

    Sin trazado, sin descripcion, sin autor. Una ruta de 300 puntos pesa aqui
    lo mismo que una de 2.
    """

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
            'latitude',
            'longitude',
        ]
        read_only_fields = fields


class RouteImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouteImage
        fields = ['id', 'url', 'order']
