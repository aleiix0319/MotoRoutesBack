from django.conf import settings
from django.db import models

from routes.models import Route

# Create your models here.
class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites'
    )

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='favorites'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'route')

    def __str__(self):
        return f"{self.user.username} - {self.route.name}"