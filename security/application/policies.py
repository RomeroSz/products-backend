from rest_framework.permissions import BasePermission


class IsActorAuthenticated(BasePermission):
    """Permiso base: exige usuario y contexto de actor (cuando exista)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
