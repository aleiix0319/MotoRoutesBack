from typing import Optional

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """UserDto del cliente.

    Los campos del Profile 1-1 se aplanan a la raiz: el cliente espera
    "avatar" y "bio" al mismo nivel que "username", no anidados.
    """

    avatar = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'avatar',
            'bio',
        ]
        read_only_fields = fields

    def get_avatar(self, obj) -> Optional[str]:
        profile = getattr(obj, 'profile', None)
        return profile.avatar if profile is not None else None

    def get_bio(self, obj) -> str:
        profile = getattr(obj, 'profile', None)
        return profile.bio if profile is not None else ''
