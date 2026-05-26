from django.db import models
from users.models import UserProfile
from routes.models import Route

# Create your models here.
class Favorite(models.Model):
    user = models.ForeignKey(
        UserProfile,
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
        return f"{self.user.name} - {self.route.name}"