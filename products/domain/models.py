from django.db import models


class Product(models.Model):
    id = models.UUIDField(primary_key=True)
    company_id = models.UUIDField(null=True)
    nombre = models.TextField()
    nombre_norm = models.TextField(null=True, blank=True)
    estado = models.TextField()  # enum en DB
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = '"core"."product"'


class VersionProduct(models.Model):
    id = models.UUIDField(primary_key=True)
    idproduct = models.UUIDField()  # FK lógico a Product
    version = models.IntegerField()
    estado = models.TextField()  # enum en DB
    locked_by_state = models.BooleanField(default=False)
    vigencia_desde = models.DateField(null=True)
    vigencia_hasta = models.DateField(null=True)

    class Meta:
        managed = False
        db_table = '"core"."version_product"'


class Documento(models.Model):
    id = models.UUIDField(primary_key=True)
    nombre = models.TextField()
    tipo = models.TextField()
    mime = models.TextField(null=True)
    archivo_url = models.TextField()
    tamano = models.BigIntegerField(null=True)
    referencia_normativa = models.TextField(null=True)
    watermark = models.TextField(null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = '"core"."documento"'


class CG(models.Model):
    id = models.UUIDField(primary_key=True)
    documento_id = models.UUIDField()
    logical_code = models.TextField()
    version = models.IntegerField()
    idramo = models.UUIDField()
    estado = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = '"core"."cg"'


class VPToCG(models.Model):
    id = models.UUIDField(primary_key=True)
    idversionproduct = models.UUIDField()
    idcg = models.UUIDField()
    estado = models.TextField()
    # vigencia es daterange -> lo manejaremos por función al crear

    class Meta:
        managed = False
        db_table = '"link"."vp_to_cg"'