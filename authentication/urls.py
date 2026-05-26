from django.urls import path

from .views import firebase_login

urlpatterns = [
    path("firebase/", firebase_login, name="firebase-login"),
]