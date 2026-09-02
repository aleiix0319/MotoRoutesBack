from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Route

User = get_user_model()


class RoutePermissionTests(APITestCase):
    """La escritura de rutas queda cerrada; la lectura sigue abierta.

    Las reglas de visibility (y los 404 que traen) llegan en Fase 2.
    """

    def setUp(self):
        self.author = User.objects.create_user(
            username='aleix',
            email='aleix@example.com',
            password='Montseny2026!',
        )
        self.other = User.objects.create_user(
            username='otro',
            email='otro@example.com',
            password='Montseny2026!',
        )
        self.author_token = Token.objects.create(user=self.author)
        self.other_token = Token.objects.create(user=self.other)

        self.route = Route.objects.create(
            user=self.author,
            name='Collformic - Montseny',
            description='Subida por Sant Celoni',
            distance=84.5,
            duration=125,
            difficulty='medium',
        )

    def as_author(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.author_token.key}'
        )

    def as_other(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.other_token.key}'
        )

    # Lectura

    def test_anonymous_can_list_routes(self):
        response = self.client.get('/api/routes/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_is_a_plain_array_not_paginated(self):
        response = self.client.get('/api/routes/')

        # El cliente deserializa esto como array JSON plano. Si algun dia
        # aparece aqui un dict con "results", se rompen todas las listas.
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)

    def test_anonymous_can_retrieve_a_route(self):
        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_route_payload_keeps_the_fields_the_client_reads(self):
        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertEqual(
            set(response.data.keys()),
            {
                'id', 'user', 'name', 'description', 'distance', 'duration',
                'difficulty', 'image', 'created_at', 'updated_at', 'points',
            },
        )

    # Escritura

    def test_anonymous_cannot_create(self):
        response = self.client.post(
            '/api/routes/',
            {
                'name': 'X',
                'description': 'Y',
                'distance': 10,
                'duration': 15,
                'difficulty': 'easy',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_author_comes_from_the_token_not_the_body(self):
        self.as_author()

        response = self.client.post(
            '/api/routes/',
            {
                'user': self.other.id,
                'name': 'Turo de l Home',
                'description': 'Por Fogars',
                'distance': 30,
                'duration': 40,
                'difficulty': 'easy',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['user'], self.author.id)

    def test_anonymous_cannot_delete(self):
        response = self.client.delete(f'/api/routes/{self.route.id}/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(Route.objects.filter(id=self.route.id).exists())

    def test_another_user_cannot_patch(self):
        self.as_other()

        response = self.client.patch(
            f'/api/routes/{self.route.id}/',
            {'name': 'Secuestrada'},
            format='json',
        )

        # 403, no 404: sobre una ruta publica la existencia no es un secreto.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.route.refresh_from_db()
        self.assertEqual(self.route.name, 'Collformic - Montseny')

    def test_another_user_cannot_delete(self):
        self.as_other()

        response = self.client.delete(f'/api/routes/{self.route.id}/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Route.objects.filter(id=self.route.id).exists())

    def test_author_can_patch_and_delete(self):
        self.as_author()

        patched = self.client.patch(
            f'/api/routes/{self.route.id}/',
            {'name': 'Collformic'},
            format='json',
        )
        self.assertEqual(patched.status_code, status.HTTP_200_OK)

        deleted = self.client.delete(f'/api/routes/{self.route.id}/')
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Route.objects.filter(id=self.route.id).exists())


class RetiredEndpointTests(APITestCase):
    """route-points/, favorites/ y reviews/ ya no estan enrutados."""

    def test_retired_endpoints_are_gone(self):
        for path in ('/api/route-points/', '/api/favorites/', '/api/reviews/'):
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.get(path).status_code,
                    status.HTTP_404_NOT_FOUND,
                )


class UserEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='aleix',
            email='aleix@example.com',
            password='Montseny2026!',
            first_name='Aleix',
        )
        self.token = Token.objects.create(user=self.user)

    def test_users_list_requires_a_token(self):
        self.assertEqual(
            self.client.get('/api/users/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_users_list_is_a_plain_array(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        response = self.client.get('/api/users/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_user_payload_is_flat(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        response = self.client.get(f'/api/users/{self.user.id}/')

        # avatar y bio salen a la raiz, no anidados bajo "profile".
        self.assertEqual(
            set(response.data.keys()),
            {
                'id', 'username', 'email', 'first_name', 'last_name',
                'avatar', 'bio',
            },
        )
        self.assertIsNone(response.data['avatar'])
        self.assertEqual(response.data['bio'], '')

    def test_users_are_read_only(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        response = self.client.post(
            '/api/users/', {'username': 'nuevo'}, format='json'
        )

        self.assertEqual(
            response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
