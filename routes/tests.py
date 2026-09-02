from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from favorites.models import Favorite
from users.models import Follow

from .geo import haversine_km
from .models import Route, RouteImage, RoutePoint

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='Montseny2026!',
    )


def make_route(author, name='Ruta', visibility=Route.VISIBILITY_PUBLIC,
               points=None):
    route = Route.objects.create(
        user=author,
        name=name,
        description='Descripcion',
        difficulty='medium',
        visibility=visibility,
    )

    for index, (latitude, longitude) in enumerate(points or []):
        RoutePoint.objects.create(
            route=route,
            latitude=latitude,
            longitude=longitude,
            order=index,
        )

    if points:
        route.recalculate_from_points()

    return route


def follow(follower, following):
    Follow.objects.create(follower=follower, following=following)


class AuthenticatedAPITestCase(APITestCase):
    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def anonymous(self):
        self.client.credentials()


# --------------------------------------------------------------------------
# Visibilidad. Un fallo aqui significa ensenar rutas privadas a quien no debe,
# asi que se cubren las tres visibilidades por cada tipo de espectador.
# --------------------------------------------------------------------------

class VisibilityTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.author = make_user('autor')
        self.mutual = make_user('mutuo')
        self.follower_only = make_user('solo_sigue')
        self.followed_only = make_user('solo_seguido')
        self.stranger = make_user('desconocido')

        # Amigos: seguimiento en los dos sentidos.
        follow(self.author, self.mutual)
        follow(self.mutual, self.author)

        # follower_only sigue al autor, pero el autor no le sigue de vuelta.
        follow(self.follower_only, self.author)

        # El autor sigue a followed_only, pero no al reves.
        follow(self.author, self.followed_only)

        self.public = make_route(
            self.author, 'Publica', Route.VISIBILITY_PUBLIC
        )
        self.friends = make_route(
            self.author, 'De amigos', Route.VISIBILITY_FRIENDS
        )
        self.private = make_route(
            self.author, 'Privada', Route.VISIBILITY_PRIVATE
        )

    def detail(self, route):
        return self.client.get(f'/api/routes/{route.id}/')

    def listed_names(self):
        response = self.client.get('/api/routes/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {route['name'] for route in response.data}

    # Anonimo

    def test_anonymous_sees_only_public(self):
        self.anonymous()

        self.assertEqual(self.listed_names(), {'Publica'})

    def test_anonymous_gets_404_on_friends_route(self):
        self.anonymous()

        self.assertEqual(
            self.detail(self.friends).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_anonymous_gets_404_on_private_route(self):
        self.anonymous()

        self.assertEqual(
            self.detail(self.private).status_code, status.HTTP_404_NOT_FOUND
        )

    # Autor

    def test_author_sees_all_three(self):
        self.authenticate(self.author)

        self.assertEqual(
            self.listed_names(), {'Publica', 'De amigos', 'Privada'}
        )

    def test_author_can_read_own_private(self):
        self.authenticate(self.author)

        self.assertEqual(
            self.detail(self.private).status_code, status.HTTP_200_OK
        )

    # Desconocido

    def test_stranger_sees_only_public(self):
        self.authenticate(self.stranger)

        self.assertEqual(self.listed_names(), {'Publica'})

    def test_stranger_gets_404_on_friends_route(self):
        self.authenticate(self.stranger)

        self.assertEqual(
            self.detail(self.friends).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_stranger_gets_404_on_private_route(self):
        self.authenticate(self.stranger)

        self.assertEqual(
            self.detail(self.private).status_code, status.HTTP_404_NOT_FOUND
        )

    # Amigo (seguimiento mutuo)

    def test_mutual_follower_sees_friends_route(self):
        self.authenticate(self.mutual)

        self.assertEqual(self.listed_names(), {'Publica', 'De amigos'})
        self.assertEqual(
            self.detail(self.friends).status_code, status.HTTP_200_OK
        )

    def test_mutual_follower_still_cannot_see_private(self):
        self.authenticate(self.mutual)

        self.assertEqual(
            self.detail(self.private).status_code, status.HTTP_404_NOT_FOUND
        )

    # Seguimiento en un solo sentido: NO es amistad

    def test_following_without_being_followed_back_is_not_friendship(self):
        self.authenticate(self.follower_only)

        self.assertEqual(self.listed_names(), {'Publica'})
        self.assertEqual(
            self.detail(self.friends).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_being_followed_without_following_back_is_not_friendship(self):
        self.authenticate(self.followed_only)

        self.assertEqual(self.listed_names(), {'Publica'})
        self.assertEqual(
            self.detail(self.friends).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_unfollowing_takes_the_friends_route_away(self):
        self.authenticate(self.mutual)
        self.assertEqual(
            self.detail(self.friends).status_code, status.HTTP_200_OK
        )

        Follow.objects.filter(
            follower=self.mutual, following=self.author
        ).delete()

        self.assertEqual(
            self.detail(self.friends).status_code, status.HTTP_404_NOT_FOUND
        )

    # Escritura sobre lo que no se puede ver: 404, nunca 403

    def test_patch_on_invisible_route_is_404_not_403(self):
        self.authenticate(self.stranger)

        response = self.client.patch(
            f'/api/routes/{self.private.id}/',
            {'name': 'Robada'},
            format='json',
        )

        # Un 403 confirmaria que la ruta existe.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_on_invisible_route_is_404_not_403(self):
        self.authenticate(self.stranger)

        response = self.client.delete(f'/api/routes/{self.private.id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Route.objects.filter(id=self.private.id).exists())

    def test_save_on_invisible_route_is_404(self):
        self.authenticate(self.stranger)

        response = self.client.post(f'/api/routes/{self.private.id}/save/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Favorite.objects.count(), 0)

    def test_patch_on_visible_but_foreign_route_is_403_not_404(self):
        self.authenticate(self.stranger)

        response = self.client.patch(
            f'/api/routes/{self.public.id}/',
            {'name': 'Robada'},
            format='json',
        )

        # Aqui la existencia no es un secreto: la ruta es publica.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_author_can_change_visibility(self):
        self.authenticate(self.author)

        response = self.client.patch(
            f'/api/routes/{self.public.id}/',
            {'visibility': 'private'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.public.refresh_from_db()
        self.assertEqual(self.public.visibility, Route.VISIBILITY_PRIVATE)

        # Y a partir de ahi el desconocido deja de verla.
        self.authenticate(self.stranger)
        self.assertEqual(
            self.detail(self.public).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_visibility_only_accepts_the_three_known_values(self):
        self.authenticate(self.author)

        response = self.client.patch(
            f'/api/routes/{self.public.id}/',
            {'visibility': 'secret'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('visibility', response.data)


class FeedVisibilityTests(AuthenticatedAPITestCase):
    """Los feeds no pueden ser una puerta trasera a la visibilidad."""

    def setUp(self):
        self.me = make_user('yo')
        self.friend = make_user('amiga')
        self.idol = make_user('idolo')

        follow(self.me, self.friend)
        follow(self.friend, self.me)

        # Sigo a idolo, pero no me sigue de vuelta.
        follow(self.me, self.idol)

        self.friend_public = make_route(
            self.friend, 'Amiga publica', Route.VISIBILITY_PUBLIC
        )
        self.friend_friends = make_route(
            self.friend, 'Amiga amigos', Route.VISIBILITY_FRIENDS
        )
        self.friend_private = make_route(
            self.friend, 'Amiga privada', Route.VISIBILITY_PRIVATE
        )

        self.idol_public = make_route(
            self.idol, 'Idolo publica', Route.VISIBILITY_PUBLIC
        )
        self.idol_friends = make_route(
            self.idol, 'Idolo amigos', Route.VISIBILITY_FRIENDS
        )

        self.mine_private = make_route(
            self.me, 'Mia privada', Route.VISIBILITY_PRIVATE
        )

    def names(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {route['name'] for route in response.data}

    def test_for_you_is_public_only_even_with_a_session(self):
        self.authenticate(self.me)

        self.assertEqual(
            self.names('/api/routes/?feed=for_you'),
            {'Amiga publica', 'Idolo publica'},
        )

    def test_for_you_works_without_a_session(self):
        self.anonymous()

        self.assertEqual(
            self.names('/api/routes/?feed=for_you'),
            {'Amiga publica', 'Idolo publica'},
        )

    def test_for_you_is_ordered_newest_first(self):
        self.anonymous()

        response = self.client.get('/api/routes/?feed=for_you')
        ids = [route['id'] for route in response.data]

        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_following_includes_friends_routes_of_mutuals(self):
        self.authenticate(self.me)

        self.assertEqual(
            self.names('/api/routes/?feed=following'),
            {'Amiga publica', 'Amiga amigos', 'Idolo publica'},
        )

    def test_following_excludes_friends_routes_of_non_mutuals(self):
        self.authenticate(self.me)

        self.assertNotIn('Idolo amigos', self.names('/api/routes/?feed=following'))

    def test_following_never_leaks_a_private_route(self):
        self.authenticate(self.me)

        self.assertNotIn(
            'Amiga privada', self.names('/api/routes/?feed=following')
        )

    def test_following_requires_a_session(self):
        self.anonymous()

        self.assertEqual(
            self.client.get('/api/routes/?feed=following').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_unknown_feed_is_a_field_error(self):
        self.anonymous()

        response = self.client.get('/api/routes/?feed=trending')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('feed', response.data)

    def test_author_me_returns_my_routes_including_private(self):
        self.authenticate(self.me)

        self.assertEqual(
            self.names('/api/routes/?author=me'), {'Mia privada'}
        )

    def test_author_me_requires_a_session(self):
        self.anonymous()

        self.assertEqual(
            self.client.get('/api/routes/?author=me').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_author_by_id_respects_visibility(self):
        self.authenticate(self.me)

        names = self.names(f'/api/routes/?author={self.idol.id}')

        self.assertEqual(names, {'Idolo publica'})

    def test_author_by_id_of_a_mutual_includes_friends_routes(self):
        self.authenticate(self.me)

        names = self.names(f'/api/routes/?author={self.friend.id}')

        self.assertEqual(names, {'Amiga publica', 'Amiga amigos'})

    def test_author_by_id_never_leaks_private_routes(self):
        self.authenticate(self.idol)

        names = self.names(f'/api/routes/?author={self.me.id}')

        self.assertEqual(names, set())

    def test_malformed_author_is_a_field_error(self):
        self.authenticate(self.me)

        response = self.client.get('/api/routes/?author=pepito')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('author', response.data)


# --------------------------------------------------------------------------
# Creacion con puntos anidados
# --------------------------------------------------------------------------

class NestedCreateTests(AuthenticatedAPITestCase):
    payload = {
        'name': 'Collformic - Montseny',
        'description': 'Subida por Sant Celoni',
        'difficulty': 'medium',
        'visibility': 'public',
        'points': [
            {'latitude': '41.7689000', 'longitude': '2.3567000', 'order': 0},
            {'latitude': '41.7934000', 'longitude': '2.4210000', 'order': 1},
        ],
    }

    def setUp(self):
        self.user = make_user('aleix')
        self.authenticate(self.user)

    def test_creates_route_and_points_in_one_request(self):
        response = self.client.post(
            '/api/routes/', self.payload, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        route = Route.objects.get()
        self.assertEqual(route.points.count(), 2)
        self.assertEqual(len(response.data['points']), 2)

    def test_author_comes_from_the_token(self):
        other = make_user('otro')

        response = self.client.post(
            '/api/routes/',
            {**self.payload, 'user': other.id, 'author': other.id},
            format='json',
        )

        self.assertEqual(response.data['user'], self.user.id)
        self.assertEqual(response.data['author']['id'], self.user.id)

    def test_server_computes_distance_and_duration(self):
        response = self.client.post(
            '/api/routes/', self.payload, format='json'
        )

        expected_km = haversine_km(
            41.7689, 2.3567, 41.7934, 2.4210
        )
        self.assertAlmostEqual(response.data['distance'], expected_km, places=2)
        self.assertEqual(
            response.data['duration'], round(expected_km / 45.0 * 60)
        )

    def test_client_sent_distance_and_duration_are_ignored(self):
        response = self.client.post(
            '/api/routes/',
            {**self.payload, 'distance': 9999.0, 'duration': 9999},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(response.data['distance'], 9999.0)
        self.assertNotEqual(response.data['duration'], 9999)

    def test_start_coordinates_are_denormalized_from_the_first_point(self):
        self.client.post('/api/routes/', self.payload, format='json')

        route = Route.objects.get()
        self.assertEqual(str(route.start_latitude), '41.7689000')
        self.assertEqual(str(route.start_longitude), '2.3567000')

    def test_order_defaults_to_the_array_position(self):
        payload = {
            **self.payload,
            'points': [
                {'latitude': '41.7689000', 'longitude': '2.3567000'},
                {'latitude': '41.7934000', 'longitude': '2.4210000'},
                {'latitude': '41.8100000', 'longitude': '2.4500000'},
            ],
        }

        response = self.client.post('/api/routes/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            list(Route.objects.get().points.values_list('order', flat=True)),
            [0, 1, 2],
        )

    def test_duplicated_order_is_a_field_error_not_a_500(self):
        payload = {
            **self.payload,
            'points': [
                {'latitude': '41.7689000', 'longitude': '2.3567000', 'order': 0},
                {'latitude': '41.7934000', 'longitude': '2.4210000', 'order': 0},
            ],
        }

        response = self.client.post('/api/routes/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('points', response.data)

    def test_a_route_needs_at_least_two_points(self):
        payload = {
            **self.payload,
            'points': [
                {'latitude': '41.7689000', 'longitude': '2.3567000', 'order': 0},
            ],
        }

        response = self.client.post('/api/routes/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('points', response.data)

    def test_nothing_is_created_when_a_point_is_invalid(self):
        payload = {
            **self.payload,
            'points': [
                {'latitude': '41.7689000', 'longitude': '2.3567000', 'order': 0},
                {'latitude': 'no-es-una-coordenada', 'longitude': '2.4', 'order': 1},
            ],
        }

        response = self.client.post('/api/routes/', payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Ni rutas a medias ni puntos huerfanos.
        self.assertEqual(Route.objects.count(), 0)
        self.assertEqual(RoutePoint.objects.count(), 0)

    def test_unknown_difficulty_is_rejected(self):
        response = self.client.post(
            '/api/routes/',
            {**self.payload, 'difficulty': 'extreme'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('difficulty', response.data)

    def test_visibility_defaults_to_public(self):
        payload = {k: v for k, v in self.payload.items() if k != 'visibility'}

        response = self.client.post('/api/routes/', payload, format='json')

        self.assertEqual(response.data['visibility'], 'public')

    def test_anonymous_cannot_create(self):
        self.anonymous()

        response = self.client.post(
            '/api/routes/', self.payload, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_replaces_the_whole_trace_and_recomputes(self):
        self.client.post('/api/routes/', self.payload, format='json')
        route = Route.objects.get()
        original_distance = route.distance

        response = self.client.patch(
            f'/api/routes/{route.id}/',
            {
                'points': [
                    {'latitude': '41.0000000', 'longitude': '2.0000000', 'order': 0},
                    {'latitude': '42.0000000', 'longitude': '2.0000000', 'order': 1},
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        route.refresh_from_db()
        self.assertEqual(route.points.count(), 2)
        self.assertNotEqual(route.distance, original_distance)

    def test_patch_without_points_leaves_the_trace_alone(self):
        self.client.post('/api/routes/', self.payload, format='json')
        route = Route.objects.get()

        self.client.patch(
            f'/api/routes/{route.id}/', {'name': 'Otro nombre'}, format='json'
        )

        route.refresh_from_db()
        self.assertEqual(route.points.count(), 2)
        self.assertEqual(route.name, 'Otro nombre')


# --------------------------------------------------------------------------
# Guardados
# --------------------------------------------------------------------------

class SaveTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.author = make_user('autor')
        self.me = make_user('yo')
        self.route = make_route(self.author, 'Publica')
        self.authenticate(self.me)

    def test_save_is_idempotent(self):
        first = self.client.post(f'/api/routes/{self.route.id}/save/')
        second = self.client.post(f'/api/routes/{self.route.id}/save/')

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data, second.data)
        self.assertEqual(Favorite.objects.count(), 1)

    def test_unsave_is_idempotent(self):
        self.client.post(f'/api/routes/{self.route.id}/save/')

        first = self.client.delete(f'/api/routes/{self.route.id}/save/')
        second = self.client.delete(f'/api/routes/{self.route.id}/save/')

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data, second.data)
        self.assertEqual(Favorite.objects.count(), 0)

    def test_save_returns_the_new_state(self):
        response = self.client.post(f'/api/routes/{self.route.id}/save/')

        self.assertEqual(response.data, {'is_saved': True, 'save_count': 1})

    def test_save_requires_a_session(self):
        self.anonymous()

        self.assertEqual(
            self.client.post(f'/api/routes/{self.route.id}/save/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_is_saved_is_per_user(self):
        self.client.post(f'/api/routes/{self.route.id}/save/')

        mine = self.client.get(f'/api/routes/{self.route.id}/')
        self.assertTrue(mine.data['is_saved'])
        self.assertEqual(mine.data['save_count'], 1)

        self.authenticate(self.author)
        theirs = self.client.get(f'/api/routes/{self.route.id}/')
        self.assertFalse(theirs.data['is_saved'])
        self.assertEqual(theirs.data['save_count'], 1)

    def test_is_saved_is_false_for_anonymous(self):
        self.client.post(f'/api/routes/{self.route.id}/save/')
        self.anonymous()

        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertFalse(response.data['is_saved'])

    def test_saved_list_returns_only_my_saved_routes(self):
        other_route = make_route(self.author, 'Otra')
        self.client.post(f'/api/routes/{self.route.id}/save/')

        response = self.client.get('/api/routes/saved/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [route['name'] for route in response.data], ['Publica']
        )
        self.assertNotIn(other_route.name, [r['name'] for r in response.data])

    def test_saved_list_requires_a_session(self):
        self.anonymous()

        self.assertEqual(
            self.client.get('/api/routes/saved/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_saved_list_drops_routes_that_stopped_being_visible(self):
        self.client.post(f'/api/routes/{self.route.id}/save/')

        self.route.visibility = Route.VISIBILITY_PRIVATE
        self.route.save(update_fields=['visibility'])

        response = self.client.get('/api/routes/saved/')

        self.assertEqual(response.data, [])


# --------------------------------------------------------------------------
# Mapa
# --------------------------------------------------------------------------

class NearTests(AuthenticatedAPITestCase):
    BARCELONA = '41.3851,2.1734'

    def setUp(self):
        self.author = make_user('autor')

        # Arranca en Barcelona.
        self.close = make_route(
            self.author, 'Cerca', points=[('41.4000', '2.2000'), ('41.45', '2.25')]
        )
        # Arranca cerca de Girona, a unos 90 km.
        self.far = make_route(
            self.author, 'Lejos', points=[('41.9794', '2.8214'), ('42.0', '2.9')]
        )
        # Privada y cerca: no debe salir ni en el mapa.
        self.hidden = make_route(
            self.author,
            'Escondida',
            visibility=Route.VISIBILITY_PRIVATE,
            points=[('41.4001', '2.2001'), ('41.45', '2.25')],
        )
        self.anonymous()

    def test_returns_only_routes_inside_the_radius(self):
        response = self.client.get(
            f'/api/routes/?near={self.BARCELONA}&radius_km=25'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [route['name'] for route in response.data], ['Cerca']
        )

    def test_a_bigger_radius_reaches_further(self):
        response = self.client.get(
            f'/api/routes/?near={self.BARCELONA}&radius_km=200'
        )

        self.assertEqual(
            {route['name'] for route in response.data}, {'Cerca', 'Lejos'}
        )

    def test_near_respects_visibility(self):
        response = self.client.get(
            f'/api/routes/?near={self.BARCELONA}&radius_km=200'
        )

        self.assertNotIn(
            'Escondida', [route['name'] for route in response.data]
        )

    def test_response_is_light(self):
        response = self.client.get(
            f'/api/routes/?near={self.BARCELONA}&radius_km=25'
        )

        self.assertEqual(
            set(response.data[0].keys()),
            {'id', 'name', 'distance', 'latitude', 'longitude'},
        )
        # Sin trazado: una ruta de 300 puntos pesa aqui lo mismo que una de 2.
        self.assertNotIn('points', response.data[0])

    def test_coordinates_come_as_strings(self):
        response = self.client.get(
            f'/api/routes/?near={self.BARCELONA}&radius_km=25'
        )

        self.assertIsInstance(response.data[0]['latitude'], str)
        self.assertIsInstance(response.data[0]['longitude'], str)

    def test_radius_defaults_to_25_km(self):
        response = self.client.get(f'/api/routes/?near={self.BARCELONA}')

        self.assertEqual(
            [route['name'] for route in response.data], ['Cerca']
        )

    def test_malformed_near_is_a_field_error(self):
        response = self.client.get('/api/routes/?near=41.3851')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('near', response.data)

    def test_out_of_range_coordinates_are_rejected(self):
        response = self.client.get('/api/routes/?near=91,2.17')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('near', response.data)

    def test_malformed_radius_is_a_field_error(self):
        response = self.client.get(
            f'/api/routes/?near={self.BARCELONA}&radius_km=mucho'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('radius_km', response.data)

    def test_routes_without_points_never_show_on_the_map(self):
        make_route(self.author, 'Sin puntos')

        response = self.client.get(
            f'/api/routes/?near={self.BARCELONA}&radius_km=500'
        )

        self.assertNotIn(
            'Sin puntos', [route['name'] for route in response.data]
        )


# --------------------------------------------------------------------------
# Forma del JSON
# --------------------------------------------------------------------------

class RoutePayloadTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.author = make_user('autor')
        self.route = make_route(
            self.author,
            'Publica',
            points=[('41.7689', '2.3567'), ('41.7934', '2.4210')],
        )
        self.anonymous()

    def test_list_is_still_a_plain_array(self):
        response = self.client.get('/api/routes/')

        # Si algun dia aparece aqui un dict con "results", se rompen todas las
        # listas del cliente a la vez.
        self.assertIsInstance(response.data, list)

    def test_payload_has_the_old_fields_and_the_new_ones(self):
        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertEqual(
            set(response.data.keys()),
            {
                # Los que ya leia el cliente: ninguno desaparece.
                'id', 'user', 'name', 'description', 'distance', 'duration',
                'difficulty', 'image', 'created_at', 'updated_at', 'points',
                # Fase 2.
                'author', 'visibility', 'images', 'is_saved', 'save_count',
            },
        )

    def test_user_and_author_point_to_the_same_person(self):
        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertEqual(response.data['user'], self.author.id)
        self.assertEqual(
            set(response.data['author'].keys()), {'id', 'username', 'avatar'}
        )
        self.assertEqual(response.data['author']['id'], self.author.id)
        self.assertIsNone(response.data['author']['avatar'])

    def test_point_coordinates_are_strings(self):
        response = self.client.get(f'/api/routes/{self.route.id}/')
        point = response.data['points'][0]

        self.assertIsInstance(point['latitude'], str)
        self.assertIsInstance(point['longitude'], str)

    def test_images_is_a_list(self):
        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertEqual(response.data['images'], [])

    def test_images_lists_the_route_images_in_order(self):
        RouteImage.objects.create(
            route=self.route, url='https://cdn/2.jpg', order=1
        )
        RouteImage.objects.create(
            route=self.route, url='https://cdn/1.jpg', order=0
        )

        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertEqual(
            response.data['images'], ['https://cdn/1.jpg', 'https://cdn/2.jpg']
        )

    def test_legacy_single_image_still_shows_up_in_images(self):
        self.route.image = 'https://cdn/vieja.jpg'
        self.route.save(update_fields=['image'])

        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertEqual(response.data['images'], ['https://cdn/vieja.jpg'])

    def test_dates_are_iso_utc_with_a_z(self):
        response = self.client.get(f'/api/routes/{self.route.id}/')

        self.assertRegex(
            response.data['created_at'],
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$',
        )


class RetiredEndpointTests(APITestCase):
    def test_retired_endpoints_are_gone(self):
        for path in ('/api/route-points/', '/api/favorites/', '/api/reviews/'):
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.get(path).status_code,
                    status.HTTP_404_NOT_FOUND,
                )


class UserEndpointTests(AuthenticatedAPITestCase):
    def setUp(self):
        self.user = make_user('aleix')

    def test_users_list_requires_a_token(self):
        self.assertEqual(
            self.client.get('/api/users/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_users_list_is_a_plain_array(self):
        self.authenticate(self.user)

        response = self.client.get('/api/users/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_user_payload_is_flat(self):
        self.authenticate(self.user)

        response = self.client.get(f'/api/users/{self.user.id}/')

        self.assertEqual(
            set(response.data.keys()),
            {
                'id', 'username', 'email', 'first_name', 'last_name',
                'avatar', 'bio',
            },
        )

    def test_users_are_read_only(self):
        self.authenticate(self.user)

        response = self.client.post(
            '/api/users/', {'username': 'nuevo'}, format='json'
        )

        self.assertEqual(
            response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )


class FollowModelTests(APITestCase):
    """El modelo existe ya porque lo necesita la visibilidad "friends".
    Los endpoints para seguir llegan en Fase 3."""

    def test_cannot_follow_the_same_person_twice(self):
        a, b = make_user('a'), make_user('b')
        follow(a, b)

        with self.assertRaises(Exception):
            follow(a, b)

    def test_cannot_follow_yourself(self):
        a = make_user('a')

        with self.assertRaises(Exception):
            follow(a, a)
