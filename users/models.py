from django.db import models

# Create your models here.
class UserProfile(models.Model):
    firebase_uid = models.CharField(max_length=128, unique=True)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)
    profile_image = models.URLField(blank=True, null=True)
    about_me = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name