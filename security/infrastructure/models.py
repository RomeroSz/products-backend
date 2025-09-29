from django.db import models

# NOTA: Todos los modelos son managed=False para NO tocar la BD.


class Role(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    code = models.TextField()  # text
    descripcion = models.TextField()  # text

    class Meta:
        managed = False
        # o '"security"."role"' si no usas search_path
        db_table = "role"

    def __str__(self):
        return f"{self.code}"


class OrgArea(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    code = models.TextField()
    name = models.TextField()

    class Meta:
        managed = False
        db_table = "org_area"

    def __str__(self):
        return f"{self.code} - {self.name}"


class Actor(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    actor_type = models.CharField(max_length=32)  # USER-DEFINED → CharField
    source_system = models.CharField(max_length=32)  # USER-DEFINED → CharField
    display_name = models.TextField()
    email = models.TextField()
    company_id = models.UUIDField(null=True, blank=True)
    org_area = models.ForeignKey(
        OrgArea,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="org_area_id",
        null=True,
        blank=True,
        related_name="actors",
    )
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "actor"

    def __str__(self):
        return self.display_name or str(self.id)


class ActorRole(models.Model):
    actor = models.ForeignKey(
        Actor,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="actor_id",
        related_name="actor_roles",
        primary_key=False,
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="role_id",
        related_name="role_actors",
        primary_key=False,
    )
    scope_type = models.CharField(max_length=32, null=True, blank=True)  # USER-DEFINED
    scope_id = models.UUIDField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "actor_role"
        unique_together = (("actor", "role", "scope_type", "scope_id"),)


class AssignmentRule(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    cargo_code = models.TextField()
    area_code = models.TextField()
    role = models.ForeignKey(
        Role,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="role_id",
        related_name="+",
    )
    org_area = models.ForeignKey(
        OrgArea,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="org_area_id",
        related_name="+",
    )

    class Meta:
        managed = False
        db_table = "assignment_rule"
