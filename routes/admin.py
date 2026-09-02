from django.contrib import admin

from .models import Route, RouteImage, RoutePoint


class RoutePointInline(admin.TabularInline):
    model = RoutePoint
    extra = 0


class RouteImageInline(admin.TabularInline):
    model = RouteImage
    extra = 0


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'visibility', 'difficulty', 'distance',
                    'duration', 'created_at')
    list_filter = ('visibility', 'difficulty')
    search_fields = ('name', 'description', 'user__username')
    readonly_fields = ('distance', 'duration', 'start_latitude',
                       'start_longitude')
    inlines = [RoutePointInline, RouteImageInline]


admin.site.register(RoutePoint)
admin.site.register(RouteImage)
