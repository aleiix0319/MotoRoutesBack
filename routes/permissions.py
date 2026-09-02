from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAuthorOrReadOnly(BasePermission):
    """Solo el autor modifica o borra su ruta.

    Devuelve 403, no 404, a proposito: sobre una ruta que el usuario ya puede
    ver, su existencia no es un secreto. El 404 se reserva para lo que no se
    puede ni saber que existe (llegara con visibility, en Fase 2).
    """

    message = 'No eres el autor de esta ruta.'

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and obj.user_id == request.user.id)
