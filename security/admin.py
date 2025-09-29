from django.contrib import admin

from security.infrastructure.models import (Actor, ActorRole, AssignmentRule,
                                            OrgArea, Role)


class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        pass

    def delete_model(self, request, obj):
        pass


@admin.register(Role)
class RoleAdmin(ReadOnlyAdmin):
    list_display = ("code", "descripcion")
    search_fields = ("code", "descripcion")


@admin.register(OrgArea)
class OrgAreaAdmin(ReadOnlyAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(Actor)
class ActorAdmin(ReadOnlyAdmin):
    list_display = (
        "display_name",
        "actor_type",
        "source_system",
        "company_id",
        "org_area",
        "created_at",
    )
    search_fields = ("display_name", "email", "actor_type", "source_system")


@admin.register(ActorRole)
class ActorRoleAdmin(ReadOnlyAdmin):
    list_display = ("actor", "role", "scope_type", "scope_id")
    search_fields = ("actor__display_name", "role__code", "scope_type")


@admin.register(AssignmentRule)
class AssignmentRuleAdmin(ReadOnlyAdmin):
    list_display = ("cargo_code", "area_code", "role", "org_area")
    search_fields = ("cargo_code", "area_code")
