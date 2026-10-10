from django.conf import settings
from django.db import models

from .geo import polyline_length_km
from .managers import RouteQuerySet

# Velocidad media asumida para estimar la duracion a partir de la distancia.
# Es el mismo criterio que usaba el cliente; si cambia, cambia aqui y solo aqui.
AVERAGE_SPEED_KMH = 45.0


class Route(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    VISIBILITY_PUBLIC = 'public'
    VISIBILITY_FRIENDS = 'friends'
    VISIBILITY_PRIVATE = 'private'

    VISIBILITY_CHOICES = [
        (VISIBILITY_PUBLIC, 'Public'),
        (VISIBILITY_FRIENDS, 'Friends'),
        (VISIBILITY_PRIVATE, 'Private'),
    ]

    # manual: trazada a mano en el mapa. recorded: grabada con el GPS, y
    # entonces la duracion es la medida por el cliente, no una estimacion.
    SOURCE_MANUAL = 'manual'
    SOURCE_RECORDED = 'recorded'

    SOURCE_CHOICES = [
        (SOURCE_MANUAL, 'Manual'),
        (SOURCE_RECORDED, 'Recorded'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='routes'
    )

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')

    # Calculadas en el servidor desde los puntos. La duracion es la excepcion
    # en las rutas grabadas: ahi manda la que mide el cliente (ver
    # RouteSerializer.validate y recalculate_from_points).
    distance = models.FloatField(default=0)
    duration = models.IntegerField(default=0)

    # Solo se fija al crear la ruta.
    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
    )

    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='easy'
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default=VISIBILITY_PUBLIC,
        db_index=True,
    )

    image = models.URLField(blank=True, null=True)

    # Coordenada del primer punto, desnormalizada. Deja el mapa de Inicio en una
    # sola consulta indexada, sin tocar la tabla de puntos.
    start_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
    )
    start_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RouteQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['start_latitude', 'start_longitude']),
        ]

    def __str__(self):
        return self.name

    def recalculate_from_points(self, commit=True):
        """Recalcula distancia, duracion y coordenada de inicio.

        Se llama al crear la ruta y cada vez que se reemplazan sus puntos.
        La duracion de una ruta grabada es la medida, no una estimacion: se
        conserva aunque cambie el trazado. Solo se estima si no la hay.
        """
        coordinates = list(
            self.points.order_by('order', 'id').values_list(
                'latitude', 'longitude'
            )
        )

        self.distance = round(polyline_length_km(coordinates), 3)
        if self.source != self.SOURCE_RECORDED or not self.duration:
            self.duration = int(
                round((self.distance / AVERAGE_SPEED_KMH) * 60)
            )

        if coordinates:
            self.start_latitude, self.start_longitude = coordinates[0]
        else:
            self.start_latitude = None
            self.start_longitude = None

        if commit:
            self.save(update_fields=[
                'distance',
                'duration',
                'start_latitude',
                'start_longitude',
                'updated_at',
            ])

        return self


class RoutePoint(models.Model):
    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='points'
    )

    # 7 decimales (~1 cm) porque es la precision que manda el cliente:
    # "41.7689000". Siguen viajando como string, nunca como float.
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    altitude = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
    )
    order = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.route.name} - Point {self.order}"

    class Meta:
        ordering = ['order']
        unique_together = ('route', 'order')


class RouteImage(models.Model):
    """Foto de una ruta.

    De momento solo guarda la URL: la subida multipart llega al final, cuando
    el cliente tenga libreria de imagenes. Hasta entonces estas filas se pueden
    crear desde el admin y el campo "images" del JSON ya funciona.
    """

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='images',
    )

    url = models.URLField()
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"{self.route.name} - Image {self.order}"
