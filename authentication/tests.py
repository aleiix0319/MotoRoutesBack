from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from users.models import Profile

User = get_user_model()


class AuthResponseShapeMixin:
    def assert_auth_payload(self, data, user):
        self.assertIn('token', data)
        self.assertIn('expires_at', data)
        self.assertIn('user', data)

        # El token no caduca en servidor: "Recuerdame" es cosa del cliente.
        self.assertIsNone(data['expires_at'])
        self.assertEqual(data['token'], Token.objects.get(user=user).key)

        self.assertEqual(
            set(data['user'].keys()),
            {
                'id', 'username', 'email', 'first_name', 'last_name',
                'avatar', 'bio',
            },
        )
        self.assertEqual(data['user']['id'], user.id)


class RegisterTests(AuthResponseShapeMixin, APITestCase):
    url = '/api/auth/register/'

    def test_creates_user_and_returns_token(self):
        response = self.client.post(
            self.url,
            {
                'username': 'aleix',
                'email': 'aleix@example.com',
                'password': 'Montseny2026!',
                'first_name': 'Aleix',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username='aleix')
        self.assert_auth_payload(response.data, user)
        self.assertTrue(user.check_password('Montseny2026!'))

    def test_creates_profile_automatically(self):
        self.client.post(
            self.url,
            {
                'username': 'aleix',
                'email': 'aleix@example.com',
                'password': 'Montseny2026!',
                'first_name': 'Aleix',
            },
            format='json',
        )

        self.assertTrue(Profile.objects.filter(user__username='aleix').exists())

    def test_duplicate_email_is_a_field_error(self):
        User.objects.create_user(
            username='otro',
            email='aleix@example.com',
            password='Montseny2026!',
        )

        response = self.client.post(
            self.url,
            {
                'username': 'aleix',
                'email': 'ALEIX@example.com',
                'password': 'Montseny2026!',
                'first_name': 'Aleix',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Contrato: {"campo": ["..."]}
        self.assertIn('email', response.data)
        self.assertIsInstance(response.data['email'], list)

    def test_duplicate_username_is_a_field_error(self):
        User.objects.create_user(username='aleix', email='a@example.com')

        response = self.client.post(
            self.url,
            {
                'username': 'aleix',
                'email': 'nuevo@example.com',
                'password': 'Montseny2026!',
                'first_name': 'Aleix',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_weak_password_is_a_field_error(self):
        response = self.client.post(
            self.url,
            {
                'username': 'aleix',
                'email': 'aleix@example.com',
                'password': '1234',
                'first_name': 'Aleix',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)


class LoginTests(AuthResponseShapeMixin, APITestCase):
    url = '/api/auth/login/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='aleix',
            email='aleix@example.com',
            password='Montseny2026!',
            first_name='Aleix',
        )

    def test_login_with_email(self):
        response = self.client.post(
            self.url,
            {'email': 'aleix@example.com', 'password': 'Montseny2026!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_auth_payload(response.data, self.user)

    def test_email_is_case_insensitive(self):
        response = self.client.post(
            self.url,
            {'email': 'ALEIX@Example.com', 'password': 'Montseny2026!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_wrong_password_is_401_with_detail(self):
        response = self.client.post(
            self.url,
            {'email': 'aleix@example.com', 'password': 'incorrecta'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)
        self.assertIsInstance(response.data['detail'], str)

    def test_unknown_email_gives_the_same_answer_as_wrong_password(self):
        response = self.client.post(
            self.url,
            {'email': 'nadie@example.com', 'password': 'Montseny2026!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            str(response.data['detail']),
            'Email o contrasena incorrectos.',
        )

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        response = self.client.post(
            self.url,
            {'email': 'aleix@example.com', 'password': 'Montseny2026!'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class MeAndLogoutTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='aleix',
            email='aleix@example.com',
            password='Montseny2026!',
        )
        self.token = Token.objects.create(user=self.user)

    def auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_me_requires_a_token(self):
        response = self.client.get('/api/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)

    def test_me_rejects_an_invalid_token(self):
        self.client.credentials(HTTP_AUTHORIZATION='Token noexiste')

        response = self.client.get('/api/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_the_user_of_the_token(self):
        self.auth()

        response = self.client.get('/api/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.user.id)
        self.assertEqual(response.data['username'], 'aleix')

    def test_logout_invalidates_the_token(self):
        self.auth()

        response = self.client.post('/api/auth/logout/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

        # El mismo token ya no sirve.
        self.assertEqual(
            self.client.get('/api/auth/me/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_logout_requires_a_token(self):
        self.assertEqual(
            self.client.post('/api/auth/logout/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class FirebaseLoginTests(AuthResponseShapeMixin, APITestCase):
    url = '/api/auth/firebase/'

    def decoded(self, uid='fb-uid-1', email='aleix@example.com', name='Aleix Montero'):
        return {'uid': uid, 'email': email, 'name': name}

    @patch('authentication.views.verify_firebase_token')
    def test_first_login_creates_user_and_profile(self, verify):
        verify.return_value = self.decoded()

        response = self.client.post(
            self.url, {'id_token': 'x'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email='aleix@example.com')
        self.assert_auth_payload(response.data, user)
        self.assertEqual(user.first_name, 'Aleix')
        self.assertEqual(user.last_name, 'Montero')
        self.assertEqual(user.profile.firebase_uid, 'fb-uid-1')
        self.assertFalse(user.has_usable_password())

    @patch('authentication.views.verify_firebase_token')
    def test_username_is_derived_from_the_email(self, verify):
        verify.return_value = self.decoded()

        self.client.post(self.url, {'id_token': 'x'}, format='json')

        self.assertTrue(User.objects.filter(username='aleix').exists())

    @patch('authentication.views.verify_firebase_token')
    def test_username_collision_gets_a_suffix(self, verify):
        User.objects.create_user(username='aleix', email='otro@example.com')
        verify.return_value = self.decoded()

        self.client.post(self.url, {'id_token': 'x'}, format='json')

        self.assertTrue(User.objects.filter(username='aleix1').exists())

    @patch('authentication.views.verify_firebase_token')
    def test_second_login_reuses_the_same_user(self, verify):
        verify.return_value = self.decoded()

        first = self.client.post(self.url, {'id_token': 'x'}, format='json')
        second = self.client.post(self.url, {'id_token': 'x'}, format='json')

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(first.data['user']['id'], second.data['user']['id'])
        self.assertEqual(first.data['token'], second.data['token'])

    @patch('authentication.views.verify_firebase_token')
    def test_firebase_uid_wins_over_a_changed_email(self, verify):
        verify.return_value = self.decoded()
        self.client.post(self.url, {'id_token': 'x'}, format='json')
        user_id = User.objects.get().id

        verify.return_value = self.decoded(email='nuevo@example.com')
        response = self.client.post(self.url, {'id_token': 'x'}, format='json')

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(response.data['user']['id'], user_id)

    @patch('authentication.views.verify_firebase_token')
    def test_existing_account_by_email_is_linked_not_duplicated(self, verify):
        existing = User.objects.create_user(
            username='aleix',
            email='aleix@example.com',
            password='Montseny2026!',
        )
        verify.return_value = self.decoded()

        response = self.client.post(self.url, {'id_token': 'x'}, format='json')

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(response.data['user']['id'], existing.id)
        existing.refresh_from_db()
        self.assertEqual(existing.profile.firebase_uid, 'fb-uid-1')

    @patch('authentication.views.verify_firebase_token')
    def test_invalid_token_is_401_with_detail(self, verify):
        verify.side_effect = ValueError('bad token')

        response = self.client.post(self.url, {'id_token': 'x'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)
        self.assertNotIn('error', response.data)

    def test_missing_id_token_is_a_field_error(self):
        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('id_token', response.data)


class PasswordResetTests(APITestCase):
    url = '/api/auth/password-reset/'

    def test_existing_account_gets_an_email_and_200(self):
        User.objects.create_user(
            username='aleix',
            email='aleix@example.com',
            password='Montseny2026!',
        )

        response = self.client.post(
            self.url, {'email': 'aleix@example.com'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_account_gets_the_same_200_and_no_email(self):
        response = self.client.post(
            self.url, {'email': 'nadie@example.com'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_two_answers_are_indistinguishable(self):
        User.objects.create_user(
            username='aleix',
            email='aleix@example.com',
            password='Montseny2026!',
        )

        known = self.client.post(
            self.url, {'email': 'aleix@example.com'}, format='json'
        )
        unknown = self.client.post(
            self.url, {'email': 'nadie@example.com'}, format='json'
        )

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data, unknown.data)

    def test_malformed_email_is_a_field_error(self):
        response = self.client.post(
            self.url, {'email': 'esto-no-es-un-email'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_reset_link_page_is_reachable(self):
        # El enlace del correo abre una pagina web servida por este Django.
        self.assertTrue(reverse('password_reset_complete'))
