from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    FriendDetailView,
    FriendListView,
    FriendRequestViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='users')
router.register(
    r'friends/requests', FriendRequestViewSet, basename='friend-requests'
)

urlpatterns = [
    path('', include(router.urls)),

    # Fuera del router: la lista de amigos no es un CRUD de filas de amistad
    # (devuelve usuarios) y se borra por id de usuario. El conversor <int:>
    # deja pasar friends/requests/ sin colisionar con friends/{user_id}/.
    path('friends/', FriendListView.as_view(), name='friends'),
    path(
        'friends/<int:user_id>/',
        FriendDetailView.as_view(),
        name='friend-detail',
    ),
]
