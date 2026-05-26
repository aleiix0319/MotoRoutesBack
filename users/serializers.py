from rest_framework import serializers
from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'id',
            'firebase_uid',
            'email',
            'name',
            'profile_image',
            'about_me',
            'created_at',
        ]