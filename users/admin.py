from django.contrib import admin

from .models import Follow, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firebase_uid', 'created_at')
    search_fields = ('user__username', 'user__email', 'firebase_uid')


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """Hasta que lleguen los endpoints de seguir (Fase 3), los follows se
    crean desde aqui para poder probar feed=following y visibility=friends."""

    list_display = ('follower', 'following', 'created_at')
    search_fields = ('follower__username', 'following__username')
    autocomplete_fields = ()
