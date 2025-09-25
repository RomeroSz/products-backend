from django.conf import settings
from django.db import models


class Role(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "security_role"  # ajusta si tu tabla difiere
        indexes = [models.Index(fields=["code"])]

    def __str__(self):
        return f"{self.code} - {self.name}"


class OrgArea(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "security_org_area"
        indexes = [models.Index(fields=["code"])]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Actor(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    type = models.CharField(max_length=16)  # INTERNAL | SR | SERVICE
    company_id = models.UUIDField(null=True, blank=True)
    display_name = models.CharField(max_length=160, blank=True, default="")
    source_system = models.CharField(max_length=32, blank=True, default="")
    external_id = models.CharField(max_length=80, blank=True, default="")
    cargo_code = models.CharField(max_length=80, blank=True, default="")
    area_code = models.CharField(max_length=80, blank=True, default="")
    org_area = models.ForeignKey(
        OrgArea,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="org_area_id",
        null=True,
        blank=True,
        related_name="actors",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "security_actor"
        indexes = [
            models.Index(fields=["type"]),
            models.Index(fields=["source_system", "external_id"]),
            models.Index(fields=["company_id"]),
        ]

    def __str__(self):
        return self.display_name or f"Actor {self.id}"


class ActorRole(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    actor = models.ForeignKey(
        Actor,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="actor_id",
        related_name="actor_roles",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="role_id",
        related_name="role_actors",
    )
    granted_at = models.DateTimeField()
    granted_by = models.UUIDField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "security_actor_role"
        unique_together = [("actor", "role")]


class UserLink(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="user_id",
        related_name="actor_link",
    )
    actor = models.OneToOneField(
        Actor,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="actor_id",
        related_name="user_link",
    )

    class Meta:
        managed = False
        db_table = "security_user_link"

    def __str__(self):
        return f"{self.user_id} ↔ {self.actor_id}"


class AssignmentRule(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    input_cargo_code = models.CharField(max_length=80)
    input_area_code = models.CharField(max_length=80, blank=True, default="")
    target_role = models.ForeignKey(
        Role,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="target_role_id",
        related_name="+",
    )
    target_org_area = models.ForeignKey(
        OrgArea,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="target_org_area_id",
        related_name="+",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "security_assignment_rule"
        indexes = [models.Index(fields=["input_cargo_code", "input_area_code"])]
