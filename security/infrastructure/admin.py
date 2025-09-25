from django.contrib import admin

from .models import Actor, ActorRole, AssignmentRule, OrgArea, Role, UserLink


class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        pass  # no-op

    def delete_model(self, request, obj):
        pass  # no-op


@admin.register(Role)
class RoleAdmin(ReadOnlyAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(OrgArea)
class OrgAreaAdmin(ReadOnlyAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(Actor)
class ActorAdmin(ReadOnlyAdmin):
    list_display = ("display_name", "type", "company_id", "org_area", "is_active")
    search_fields = (
        "display_name",
        "source_system",
        "external_id",
        "cargo_code",
        "area_code",
    )
    list_filter = ("type", "is_active")


@admin.register(ActorRole)
class ActorRoleAdmin(ReadOnlyAdmin):
    list_display = ("actor", "role", "granted_at")
    search_fields = ("actor__display_name", "role__code")


@admin.register(AssignmentRule)
class AssignmentRuleAdmin(ReadOnlyAdmin):
    list_display = (
        "input_cargo_code",
        "input_area_code",
        "target_role",
        "target_org_area",
        "is_active",
    )
    list_filter = ("is_active", "target_role", "target_org_area")
    search_fields = ("input_cargo_code", "input_area_code")


@admin.register(UserLink)
class UserLinkAdmin(ReadOnlyAdmin):
    list_display = ("user", "actor")
    search_fields = ("user__username", "actor__display_name")
