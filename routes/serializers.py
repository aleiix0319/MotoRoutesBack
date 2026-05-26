from rest_framework import serializers
from .models import Route, RoutePoint


class RoutePointSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoutePoint
        fields = [
            'id',
            'latitude',
            'longitude',
            'altitude',
            'order',
        ]


class RouteSerializer(serializers.ModelSerializer):
    points = RoutePointSerializer(many=True, read_only=True)

    class Meta:
        model = Route
        fields = [
            'id',
            'user',
            'name',
            'description',
            'distance',
            'duration',
            'difficulty',
            'image',
            'created_at',
            'updated_at',
            'points',
        ]

