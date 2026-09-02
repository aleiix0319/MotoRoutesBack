from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'firebase_uid', 'created_at')
    search_fields = ('user__username', 'user__email', 'firebase_uid')
