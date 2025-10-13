# security/api/serializers/auth.py
from typing import Any, Dict
from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers

User = get_user_model()


class SignInSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs: Dict[str, Any]):
        email = attrs.get("email")
        password = attrs.get("password")
        if not email or not password:
            raise serializers.ValidationError("Credenciales incompletas.")

        # IMPORTANTE: si tu AUTH_USER_MODEL usa `username` como USERNAME_FIELD,
        # necesitamos mapear por email -> username para authenticate().
        try:
            user_obj = User.objects.get(email__iexact=email)
            username = getattr(
                user_obj, User.USERNAME_FIELD, user_obj.username)
        except User.DoesNotExist:
            # caer a authenticate con email si tu modelo ya usa email como USERNAME_FIELD
            username = email

        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError("Credenciales inválidas.")

        attrs["user"] = user
        return attrs


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class UserMeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField(allow_null=True)
    name = serializers.CharField(source="get_full_name", allow_null=True)
    username = serializers.CharField()
