from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from users.serializers import UserMeSerializer

User = get_user_model()


class FirebaseLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True)


class LoginSerializer(serializers.Serializer):
    """Login por email + password.

    auth.User no garantiza email unico, asi que resolvemos email -> username y
    dejamos que authenticate() haga el resto (respeta is_active y backends).
    """

    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        user = (
            User.objects
            .filter(email__iexact=attrs['email'])
            .order_by('id')
            .first()
        )

        authenticated = None
        if user is not None:
            authenticated = authenticate(
                request=self.context.get('request'),
                username=user.username,
                password=attrs['password'],
            )

        if authenticated is None:
            # Mismo mensaje exista o no la cuenta: no confirmamos que emails
            # estan registrados. 401 + {"detail": "..."}, no error de campo.
            raise AuthenticationFailed('Email o contrasena incorrectos.')

        attrs['user'] = authenticated
        return attrs


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    first_name = serializers.CharField(required=True, allow_blank=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name']
        extra_kwargs = {
            'email': {'required': True, 'allow_blank': False},
            'last_name': {'required': False, 'allow_blank': True},
        }

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                'Ya existe una cuenta con este email.'
            )
        return value

    def validate(self, attrs):
        # Se valida con el usuario a medio construir para que los validadores
        # de similitud comparen contra username / email / nombre.
        candidate = User(
            username=attrs.get('username', ''),
            email=attrs.get('email', ''),
            first_name=attrs.get('first_name', ''),
        )
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class AuthResponseSerializer(serializers.Serializer):
    """Respuesta comun de firebase/, login/ y register/. Solo documentacion."""

    token = serializers.CharField()
    expires_at = serializers.DateTimeField(
        allow_null=True,
        help_text='null si el token no caduca.',
    )
    user = UserMeSerializer()


class DetailSerializer(serializers.Serializer):
    """Cuerpo de los errores y avisos generales. Solo documentacion."""

    detail = serializers.CharField()
