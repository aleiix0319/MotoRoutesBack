from django.contrib import admin

from .models import Friendship, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firebase_uid', 'created_at')
    search_fields = ('user__username', 'user__email', 'firebase_uid')


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    """Util para montar datos de prueba sin pasar por los endpoints: aqui se
    puede dejar una amistad en 'accepted' de un tiron."""

    list_display = ('from_user', 'to_user', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('from_user__username', 'to_user__username')
