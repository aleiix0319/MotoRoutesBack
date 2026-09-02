import firebase_admin
from django.utils import timezone
from firebase_admin import auth, credentials
from rest_framework.authtoken.models import Token

from users.serializers import UserSerializer

# El token de DRF no caduca en servidor: "Recuerdame" es una decision de
# cliente (guardarlo en Keychain / EncryptedSharedPreferences o solo en
# memoria). Si algun dia queremos caducidad, se calcula aqui y solo aqui.
TOKEN_TTL = None


def initialize_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase-service-account.json")
        firebase_admin.initialize_app(cred)


def verify_firebase_token(id_token: str):
    initialize_firebase()
    return auth.verify_id_token(id_token)


def _iso_utc(value):
    """ISO-8601 en UTC sin microsegundos: 2026-08-14T09:12:00Z."""
    if value is None:
        return None
    return timezone.localtime(value, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def issue_token(user):
    """Devuelve (clave, expires_at) del token del usuario.

    authtoken es un token por usuario: si el mismo usuario entra desde dos
    dispositivos, comparten clave y el logout de uno tumba el otro.
    """
    token, _ = Token.objects.get_or_create(user=user)

    expires_at = None
    if TOKEN_TTL is not None:
        expires_at = token.created + TOKEN_TTL

    return token.key, expires_at


def auth_payload(user):
    """Cuerpo comun de firebase/, login/ y register/."""
    key, expires_at = issue_token(user)

    return {
        'token': key,
        'expires_at': _iso_utc(expires_at),
        'user': UserSerializer(user).data,
    }
