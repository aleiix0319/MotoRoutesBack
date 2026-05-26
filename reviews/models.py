from django.db import models
from users.models import UserProfile
from routes.models import Route

# Create your models here.
class Review(models.Model):
    user = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='reviews'
    )

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='reviews'
    )

    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'route')

    def __str__(self):
        return f"{self.user.name} - {self.route.name} ({self.rating})"