from rest_framework import serializers


class FirebaseLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True)