from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from users.models import Profile
from users.serializers import UserSerializer
from users.services import generate_unique_username

from .serializers import (
    AuthResponseSerializer,
    DetailSerializer,
    FirebaseLoginSerializer,
    LoginSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
)
from .services import auth_payload, verify_firebase_token

User = get_user_model()


@extend_schema(
    request=FirebaseLoginSerializer,
    responses={200: AuthResponseSerializer, 401: DetailSerializer},
)
@api_view(["POST"])
@permission_classes([AllowAny])
def firebase_login(request):
    """POST auth/firebase/ -> {token, expires_at, user}."""
    serializer = FirebaseLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        decoded_token = verify_firebase_token(
            serializer.validated_data["id_token"]
        )
    except Exception:
        raise AuthenticationFailed('Token de Firebase invalido.')

    firebase_uid = decoded_token.get("uid")
    email = decoded_token.get("email")
    name = decoded_token.get("name") or ""

    if not firebase_uid:
        raise AuthenticationFailed('El token de Firebase no trae uid.')

    if not email:
        return Response(
            {"detail": "El token de Firebase no trae email."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = _get_or_create_firebase_user(firebase_uid, email, name)

    return Response(auth_payload(user), status=status.HTTP_200_OK)


@transaction.atomic
def _get_or_create_firebase_user(firebase_uid, email, name):
    """Resuelve el auth.User detras de una cuenta de Firebase.

    Primero por firebase_uid (identidad estable aunque cambie el email), luego
    por email (cuenta creada antes por register/) y si no, alta nueva con un
    username derivado del email que el usuario podra cambiar despues.
    """
    profile = (
        Profile.objects
        .select_related('user')
        .filter(firebase_uid=firebase_uid)
        .first()
    )
    if profile is not None:
        return profile.user

    user = User.objects.filter(email__iexact=email).order_by('id').first()

    if user is None:
        first_name, _, last_name = name.partition(' ')
        user = User.objects.create_user(
            username=generate_unique_username(email),
            email=email,
            first_name=first_name[:150],
            last_name=last_name[:150],
        )
        # Alta solo por Firebase: no hay contrasena utilizable en este backend.
        user.set_unusable_password()
        user.save(update_fields=['password'])

    Profile.objects.update_or_create(
        user=user,
        defaults={'firebase_uid': firebase_uid},
    )

    return user


@extend_schema(
    request=LoginSerializer,
    responses={200: AuthResponseSerializer, 401: DetailSerializer},
)
@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    """POST auth/login/ con {email, password}."""
    serializer = LoginSerializer(
        data=request.data,
        context={'request': request},
    )
    serializer.is_valid(raise_exception=True)

    return Response(
        auth_payload(serializer.validated_data['user']),
        status=status.HTTP_200_OK,
    )


@extend_schema(
    request=RegisterSerializer,
    responses={201: AuthResponseSerializer},
)
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """POST auth/register/ con {username, email, password, first_name}."""
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = serializer.save()

    return Response(auth_payload(user), status=status.HTTP_201_CREATED)


@extend_schema(
    responses={200: UserSerializer, 401: DetailSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """GET auth/me/ -> UserDto del token. 401 si el token no vale."""
    return Response(
        UserSerializer(request.user).data,
        status=status.HTTP_200_OK,
    )


@extend_schema(
    request=None,
    responses={200: DetailSerializer, 401: DetailSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    """POST auth/logout/ -> invalida el token en servidor."""
    Token.objects.filter(user=request.user).delete()

    return Response({"detail": "Sesion cerrada."}, status=status.HTTP_200_OK)


@extend_schema(
    request=PasswordResetSerializer,
    responses={200: DetailSerializer},
)
@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset(request):
    """POST auth/password-reset/ con {email}.

    Responde 200 exista o no la cuenta: no filtramos que emails estan dados de
    alta. Si existe, sale un correo con un enlace a la pagina web de cambio.
    """
    serializer = PasswordResetSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    form = PasswordResetForm(data={'email': serializer.validated_data['email']})
    if form.is_valid():
        form.save(
            request=request,
            use_https=request.is_secure(),
            subject_template_name='registration/password_reset_subject.txt',
            email_template_name='registration/password_reset_email.html',
        )

    return Response(
        {
            "detail": (
                "Si existe una cuenta con ese email, recibiras un correo con "
                "instrucciones."
            )
        },
        status=status.HTTP_200_OK,
    )
