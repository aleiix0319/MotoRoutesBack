from django.urls import path

from .views import (
    firebase_login,
    login,
    logout,
    me,
    password_reset,
    register,
)

urlpatterns = [
    path("firebase/", firebase_login, name="firebase-login"),
    path("login/", login, name="login"),
    path("register/", register, name="register"),
    path("me/", me, name="me"),
    path("logout/", logout, name="logout"),
    path("password-reset/", password_reset, name="password-reset"),
]
