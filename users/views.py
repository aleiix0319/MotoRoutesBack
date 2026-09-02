from django.contrib.auth import get_user_model
from rest_framework import viewsets

from .serializers import UserSerializer

User = get_user_model()


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """GET users/ y GET users/{id}/.

    Solo lectura: las altas van por authentication (register / firebase) y la
    edicion del propio perfil llegara en PATCH users/me/ (Fase 3).
    """

    serializer_class = UserSerializer
    queryset = (
        User.objects
        .filter(is_active=True)
        .select_related('profile')
        .order_by('id')
    )
