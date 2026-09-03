from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from notifications.models import Notification
from routes.models import Route

from .models import Friendship

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='Montseny2026!',
    )


def make_route(author, name='Ruta', visibility=Route.VISIBILITY_PUBLIC):
    return Route.objects.create(
        user=author,
        name=name,
        description='Descripcion',
        difficulty='medium',
        visibility=visibility,
    )


class SocialAPITestCase(APITestCase):
    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def anonymous(self):
        self.client.credentials()

    def send_request(self, to_user):
        return self.client.post(
            '/api/friends/requests/',
            {'to_user': to_user.id},
            format='json',
        )


# --------------------------------------------------------------------------
# Enviar solicitud
# --------------------------------------------------------------------------

class FriendRequestCreateTests(SocialAPITestCase):
    def setUp(self):
        self.me = make_user('yo')
        self.other = make_user('otra')
        self.authenticate(self.me)

    def test_creates_a_pending_request(self):
        response = self.send_request(self.other)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], Friendship.STATUS_PENDING)
        self.assertEqual(response.data['from_user']['id'], self.me.id)
        self.assertEqual(response.data['to_user']['id'], self.other.id)

    def test_the_request_reaches_the_other_persons_bell(self):
        self.send_request(self.other)

        notification = Notification.objects.get(recipient=self.other)

        self.assertEqual(
            notification.type, Notification.TYPE_FRIEND_REQUEST
        )
        self.assertEqual(notification.actor, self.me)
        self.assertFalse(notification.is_read)

    def test_repeating_a_request_is_not_an_error(self):
        first = self.send_request(self.other)
        second = self.send_request(self.other)

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data['id'], first.data['id'])
        self.assertEqual(Friendship.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_crossed_requests_end_up_as_a_friendship(self):
        # La otra persona me la pide primero, y yo se la pido sin haber visto
        # la suya: no puede acabar en dos filas.
        Friendship.objects.create(from_user=self.other, to_user=self.me)

        response = self.send_request(self.other)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Friendship.STATUS_ACCEPTED)
        self.assertEqual(Friendship.objects.count(), 1)

    def test_requesting_someone_who_is_already_a_friend_is_not_an_error(self):
        Friendship.objects.create(
            from_user=self.other,
            to_user=self.me,
            status=Friendship.STATUS_ACCEPTED,
        )

        response = self.send_request(self.other)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Friendship.STATUS_ACCEPTED)
        self.assertEqual(Friendship.objects.count(), 1)

    def test_cannot_request_yourself(self):
        response = self.send_request(self.me)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('to_user', response.data)

    def test_unknown_user_is_a_field_error(self):
        response = self.client.post(
            '/api/friends/requests/', {'to_user': 9999}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('to_user', response.data)

    def test_requires_a_token(self):
        self.anonymous()

        self.assertEqual(
            self.send_request(self.other).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


# --------------------------------------------------------------------------
# Listar solicitudes
# --------------------------------------------------------------------------

class FriendRequestListTests(SocialAPITestCase):
    def setUp(self):
        self.me = make_user('yo')
        self.sender = make_user('quien_pide')
        self.target = make_user('a_quien_pido')
        self.friend = make_user('amiga')

        self.incoming = Friendship.objects.create(
            from_user=self.sender, to_user=self.me
        )
        self.outgoing = Friendship.objects.create(
            from_user=self.me, to_user=self.target
        )
        Friendship.objects.create(
            from_user=self.me,
            to_user=self.friend,
            status=Friendship.STATUS_ACCEPTED,
        )

        self.authenticate(self.me)

    def ids(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [row['id'] for row in response.data]

    def test_incoming_only_lists_requests_sent_to_me(self):
        self.assertEqual(
            self.ids('/api/friends/requests/?direction=incoming'),
            [self.incoming.id],
        )

    def test_outgoing_only_lists_requests_i_sent(self):
        self.assertEqual(
            self.ids('/api/friends/requests/?direction=outgoing'),
            [self.outgoing.id],
        )

    def test_incoming_is_the_default(self):
        self.assertEqual(
            self.ids('/api/friends/requests/'), [self.incoming.id]
        )

    def test_accepted_friendships_are_not_pending_requests(self):
        listed = (
            self.ids('/api/friends/requests/?direction=incoming')
            + self.ids('/api/friends/requests/?direction=outgoing')
        )

        self.assertEqual(len(listed), 2)

    def test_unknown_direction_is_a_field_error(self):
        response = self.client.get('/api/friends/requests/?direction=todas')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('direction', response.data)


# --------------------------------------------------------------------------
# Aceptar, rechazar y cancelar
# --------------------------------------------------------------------------

class FriendRequestResolveTests(SocialAPITestCase):
    def setUp(self):
        self.sender = make_user('quien_pide')
        self.me = make_user('yo')
        self.stranger = make_user('desconocida')

        self.friendship = Friendship.objects.create(
            from_user=self.sender, to_user=self.me
        )
        self.notification = Notification.objects.create(
            recipient=self.me,
            actor=self.sender,
            type=Notification.TYPE_FRIEND_REQUEST,
            friendship=self.friendship,
        )

    def accept(self):
        return self.client.post(
            f'/api/friends/requests/{self.friendship.id}/accept/'
        )

    def test_the_recipient_can_accept(self):
        self.authenticate(self.me)

        response = self.accept()
        self.friendship.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Friendship.STATUS_ACCEPTED)
        self.assertEqual(
            self.friendship.status, Friendship.STATUS_ACCEPTED
        )
        self.assertIsNotNone(self.friendship.responded_at)

    def test_accepting_clears_the_request_notification(self):
        self.authenticate(self.me)

        self.accept()

        # La de "te ha enviado una solicitud" ya no es accionable: se va.
        self.assertFalse(
            Notification.objects.filter(id=self.notification.id).exists()
        )

    def test_accepting_tells_the_person_who_asked(self):
        self.authenticate(self.me)

        self.accept()

        notification = Notification.objects.get(recipient=self.sender)

        self.assertEqual(
            notification.type, Notification.TYPE_FRIEND_REQUEST_ACCEPTED
        )
        self.assertEqual(notification.actor, self.me)
        self.assertEqual(notification.friendship_id, self.friendship.id)

    def test_accepting_twice_is_not_an_error(self):
        self.authenticate(self.me)
        self.accept()

        response = self.accept()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Notification.objects.filter(recipient=self.sender).count(), 1
        )

    def test_the_sender_cannot_accept_their_own_request(self):
        self.authenticate(self.sender)

        self.assertEqual(self.accept().status_code, status.HTTP_404_NOT_FOUND)

    def test_a_stranger_gets_404_not_403(self):
        self.authenticate(self.stranger)

        self.assertEqual(self.accept().status_code, status.HTTP_404_NOT_FOUND)

    def test_the_recipient_can_reject(self):
        self.authenticate(self.me)

        response = self.client.delete(
            f'/api/friends/requests/{self.friendship.id}/'
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Friendship.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_the_sender_can_cancel(self):
        self.authenticate(self.sender)

        response = self.client.delete(
            f'/api/friends/requests/{self.friendship.id}/'
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Friendship.objects.exists())

    def test_a_stranger_cannot_delete_the_request(self):
        self.authenticate(self.stranger)

        response = self.client.delete(
            f'/api/friends/requests/{self.friendship.id}/'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Friendship.objects.exists())

    def test_rejecting_lets_the_other_person_ask_again(self):
        self.authenticate(self.me)
        self.client.delete(f'/api/friends/requests/{self.friendship.id}/')

        self.authenticate(self.sender)
        response = self.send_request(self.me)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


# --------------------------------------------------------------------------
# Lista de amigos y deshacer amistad
# --------------------------------------------------------------------------

class FriendListTests(SocialAPITestCase):
    def setUp(self):
        self.me = make_user('yo')
        self.friend = make_user('amiga')
        self.other = make_user('otra')

        Friendship.objects.create(
            from_user=self.friend,
            to_user=self.me,
            status=Friendship.STATUS_ACCEPTED,
        )
        Friendship.objects.create(
            from_user=self.other,
            to_user=self.friend,
            status=Friendship.STATUS_ACCEPTED,
        )
        # Pendiente: no cuenta como amistad.
        Friendship.objects.create(from_user=self.me, to_user=self.other)

        self.authenticate(self.me)

    def usernames(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {row['username'] for row in response.data}

    def test_my_friends_regardless_of_who_asked(self):
        self.assertEqual(self.usernames('/api/friends/'), {'amiga'})

    def test_someone_elses_friends(self):
        self.assertEqual(
            self.usernames(f'/api/friends/?user={self.friend.id}'),
            {'yo', 'otra'},
        )

    def test_pending_requests_are_not_friends(self):
        self.assertNotIn('otra', self.usernames('/api/friends/'))

    def test_the_list_is_user_dtos(self):
        response = self.client.get('/api/friends/')

        self.assertEqual(
            response.data[0]['friendship_status'], 'friends'
        )

    def test_requires_a_token(self):
        self.anonymous()

        self.assertEqual(
            self.client.get('/api/friends/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_unfriending_by_user_id(self):
        response = self.client.delete(f'/api/friends/{self.friend.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.usernames('/api/friends/'), set())

    def test_unfriending_twice_is_not_an_error(self):
        self.client.delete(f'/api/friends/{self.friend.id}/')

        self.assertEqual(
            self.client.delete(f'/api/friends/{self.friend.id}/').status_code,
            status.HTTP_204_NO_CONTENT,
        )

    def test_unfriending_does_not_touch_the_pending_request(self):
        self.client.delete(f'/api/friends/{self.other.id}/')

        self.assertTrue(
            Friendship.objects
            .filter(from_user=self.me, to_user=self.other)
            .exists()
        )


# --------------------------------------------------------------------------
# UserDto: lo que necesita la pantalla de perfil ajeno
# --------------------------------------------------------------------------

class UserProfileDtoTests(SocialAPITestCase):
    def setUp(self):
        self.me = make_user('yo')
        self.other = make_user('otra')
        self.authenticate(self.me)

    def profile(self, user):
        response = self.client.get(f'/api/users/{user.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_status_none_when_there_is_nothing_between_us(self):
        data = self.profile(self.other)

        self.assertEqual(data['friendship_status'], 'none')
        self.assertIsNone(data['friendship_id'])
        self.assertFalse(data['is_me'])

    def test_status_pending_sent(self):
        friendship = Friendship.objects.create(
            from_user=self.me, to_user=self.other
        )

        data = self.profile(self.other)

        self.assertEqual(data['friendship_status'], 'pending_sent')
        self.assertEqual(data['friendship_id'], friendship.id)

    def test_status_pending_received(self):
        friendship = Friendship.objects.create(
            from_user=self.other, to_user=self.me
        )

        data = self.profile(self.other)

        self.assertEqual(data['friendship_status'], 'pending_received')
        self.assertEqual(data['friendship_id'], friendship.id)

    def test_status_friends(self):
        Friendship.objects.create(
            from_user=self.other,
            to_user=self.me,
            status=Friendship.STATUS_ACCEPTED,
        )

        self.assertEqual(
            self.profile(self.other)['friendship_status'], 'friends'
        )

    def test_my_own_profile_is_flagged(self):
        data = self.profile(self.me)

        self.assertTrue(data['is_me'])
        self.assertEqual(data['friendship_status'], 'none')

    def test_route_count_only_counts_what_i_can_see(self):
        make_route(self.other, 'Publica', Route.VISIBILITY_PUBLIC)
        make_route(self.other, 'De amigos', Route.VISIBILITY_FRIENDS)
        make_route(self.other, 'Privada', Route.VISIBILITY_PRIVATE)

        self.assertEqual(self.profile(self.other)['route_count'], 1)

    def test_route_count_grows_when_we_become_friends(self):
        make_route(self.other, 'Publica', Route.VISIBILITY_PUBLIC)
        make_route(self.other, 'De amigos', Route.VISIBILITY_FRIENDS)

        Friendship.objects.create(
            from_user=self.me,
            to_user=self.other,
            status=Friendship.STATUS_ACCEPTED,
        )

        self.assertEqual(self.profile(self.other)['route_count'], 2)

    def test_friend_count_looks_at_both_ends(self):
        third = make_user('tercera')

        Friendship.objects.create(
            from_user=self.other,
            to_user=self.me,
            status=Friendship.STATUS_ACCEPTED,
        )
        Friendship.objects.create(
            from_user=third,
            to_user=self.other,
            status=Friendship.STATUS_ACCEPTED,
        )
        # Pendiente: no suma.
        Friendship.objects.create(from_user=self.other, to_user=third)

        self.assertEqual(self.profile(self.other)['friend_count'], 2)

    def test_the_public_profile_does_not_leak_the_email(self):
        self.assertNotIn('email', self.profile(self.other))

    def test_my_own_email_still_travels_in_auth_me(self):
        response = self.client.get('/api/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.me.email)
        self.assertTrue(response.data['is_me'])


# --------------------------------------------------------------------------
# Campana de notificaciones
# --------------------------------------------------------------------------

class NotificationTests(SocialAPITestCase):
    def setUp(self):
        self.me = make_user('yo')
        self.other = make_user('otra')

        self.friendship = Friendship.objects.create(
            from_user=self.other, to_user=self.me
        )
        self.mine = Notification.objects.create(
            recipient=self.me,
            actor=self.other,
            type=Notification.TYPE_FRIEND_REQUEST,
            friendship=self.friendship,
        )
        self.theirs = Notification.objects.create(
            recipient=self.other,
            actor=self.me,
            type=Notification.TYPE_FRIEND_REQUEST_ACCEPTED,
        )

        self.authenticate(self.me)

    def test_i_only_see_my_own(self):
        response = self.client.get('/api/notifications/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in response.data], [self.mine.id])

    def test_the_payload_carries_actor_and_friendship(self):
        row = self.client.get('/api/notifications/').data[0]

        self.assertEqual(
            set(row.keys()),
            {'id', 'type', 'actor', 'friendship_id', 'is_read', 'created_at'},
        )
        self.assertEqual(row['actor']['username'], 'otra')
        self.assertEqual(row['friendship_id'], self.friendship.id)

    def test_newest_first(self):
        newer = Notification.objects.create(
            recipient=self.me,
            actor=self.other,
            type=Notification.TYPE_FRIEND_REQUEST_ACCEPTED,
        )

        ids = [row['id'] for row in self.client.get('/api/notifications/').data]

        self.assertEqual(ids[0], newer.id)

    def test_unread_count(self):
        response = self.client.get('/api/notifications/unread_count/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'count': 1})

    def test_marking_one_as_read(self):
        response = self.client.post(
            f'/api/notifications/{self.mine.id}/read/'
        )
        self.mine.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_read'])
        self.assertTrue(self.mine.is_read)

    def test_cannot_mark_someone_elses_as_read(self):
        response = self.client.post(
            f'/api/notifications/{self.theirs.id}/read/'
        )
        self.theirs.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(self.theirs.is_read)

    def test_marking_all_as_read(self):
        Notification.objects.create(
            recipient=self.me,
            actor=self.other,
            type=Notification.TYPE_FRIEND_REQUEST_ACCEPTED,
        )

        response = self.client.post('/api/notifications/read_all/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'count': 0})
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.me, is_read=False
            ).exists()
        )
        # No toca las de nadie mas.
        self.theirs.refresh_from_db()
        self.assertFalse(self.theirs.is_read)

    def test_requires_a_token(self):
        self.anonymous()

        self.assertEqual(
            self.client.get('/api/notifications/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_unfriending_leaves_the_informative_notification_alive(self):
        friendship = Friendship.objects.create(
            from_user=self.me,
            to_user=self.other,
            status=Friendship.STATUS_ACCEPTED,
        )
        notification = Notification.objects.create(
            recipient=self.me,
            actor=self.other,
            type=Notification.TYPE_FRIEND_REQUEST_ACCEPTED,
            friendship=friendship,
        )

        self.client.delete(f'/api/friends/{self.other.id}/')
        notification.refresh_from_db()

        self.assertIsNone(notification.friendship_id)
