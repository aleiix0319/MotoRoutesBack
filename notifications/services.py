from .models import Notification


def notify_friend_request(friendship):
    """Aviso accionable: "X te ha enviado una solicitud"."""
    return Notification.objects.create(
        recipient=friendship.to_user,
        actor=friendship.from_user,
        type=Notification.TYPE_FRIEND_REQUEST,
        friendship=friendship,
    )


def notify_friend_request_accepted(friendship):
    """Aviso informativo para quien pidio la amistad: "X la ha aceptado"."""
    return Notification.objects.create(
        recipient=friendship.from_user,
        actor=friendship.to_user,
        type=Notification.TYPE_FRIEND_REQUEST_ACCEPTED,
        friendship=friendship,
    )


def drop_friend_request_notification(friendship):
    """Borra el aviso de solicitud cuando deja de ser accionable.

    Al aceptar o rechazar, el boton "Aceptar" de esa fila ya no hace nada. Se
    borra en la misma transaccion que resuelve la solicitud para que el
    cliente no llegue a pintarlo. El aviso de 'friend_request_accepted' no se
    toca: es informativo y se queda.
    """
    return Notification.objects.filter(
        friendship=friendship,
        type=Notification.TYPE_FRIEND_REQUEST,
    ).delete()
