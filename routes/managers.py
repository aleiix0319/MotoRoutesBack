from django.db import models
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, Value


class RouteQuerySet(models.QuerySet):

    def visible_to(self, user):
        """Recorta a lo que `user` tiene derecho a ver.

        Es el unico sitio donde se decide la visibilidad. Todo lo que llegue a
        una vista pasa por aqui, asi que una ruta que el usuario no puede ver
        simplemente no existe para el ORM: get_object() devuelve 404 solo, sin
        que nadie tenga que acordarse de comprobarlo.
        """
        from users.services import mutual_follow_ids

        from .models import Route

        if not getattr(user, 'is_authenticated', False):
            return self.filter(visibility=Route.VISIBILITY_PUBLIC)

        return self.filter(
            Q(visibility=Route.VISIBILITY_PUBLIC)
            # Lo mio lo veo siempre, sea cual sea su visibilidad.
            | Q(user=user)
            | Q(
                visibility=Route.VISIBILITY_FRIENDS,
                user_id__in=mutual_follow_ids(user),
            )
        )

    def authored_by(self, user):
        return self.filter(user=user)

    def with_save_state(self, user):
        """Anota is_saved y save_count sin una segunda llamada del cliente."""
        from favorites.models import Favorite

        queryset = self.annotate(
            save_count=Count('favorites', distinct=True),
        )

        if not getattr(user, 'is_authenticated', False):
            return queryset.annotate(
                is_saved=Value(False, output_field=BooleanField()),
            )

        return queryset.annotate(
            is_saved=Exists(
                Favorite.objects.filter(route=OuterRef('pk'), user=user)
            ),
        )

    def for_feed(self):
        return self.order_by('-created_at', '-id')

    def in_bounding_box(self, min_lat, max_lat, min_lon, max_lon):
        """Prefiltro indexable por caja. El radio exacto se afina en Python."""
        return self.filter(
            start_latitude__isnull=False,
            start_longitude__isnull=False,
            start_latitude__gte=min_lat,
            start_latitude__lte=max_lat,
            start_longitude__gte=min_lon,
            start_longitude__lte=max_lon,
        )
