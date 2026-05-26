from django.db import models

# Create your models here.
from users.models import UserProfile

class Route(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]

    user = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='routes'
    )

    name = models.CharField(max_length=255)
    description = models.TextField()

    distance = models.FloatField()
    duration = models.IntegerField()  

    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='easy'
    )

    image = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class RoutePoint(models.Model):
    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='points'
    )

    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    altitude = models.FloatField(blank=True, null=True)
    order = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.route.name} - Point {self.order}"

    class Meta:
        ordering = ['order']
        unique_together = ('route', 'order')