from rest_framework import serializers


# ---------- START ----------
class WizardStartSerializer(serializers.Serializer):
    company_id = serializers.UUIDField()
    nombre_comercial = serializers.CharField(max_length=255)
    nombre_tecnico = serializers.CharField(max_length=255)
    ramos_actuariales = serializers.ListField(
        child=serializers.UUIDField(), min_length=1
    )
    ramos_contables = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    monedas = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    modalidades = serializers.ListField(child=serializers.UUIDField(), min_length=1)


# ---------- DOCS (CG/CP/ANNEX/FORMAT) ----------
class DocPayloadSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=255)
    tipo = serializers.CharField(max_length=32)
    mime = serializers.CharField(max_length=128)
    archivo_url = serializers.CharField(max_length=1024)
    tamano = serializers.IntegerField(min_value=1)
    referencia_normativa = serializers.CharField(
        max_length=1024, allow_null=True, allow_blank=True, required=False
    )
    watermark = serializers.CharField(
        max_length=255, allow_null=True, allow_blank=True, required=False
    )


class ItemBaseSerializer(serializers.Serializer):
    logical_code = serializers.CharField(max_length=64)
    version = serializers.IntegerField(min_value=1)


class ItemWithRamoSerializer(ItemBaseSerializer):
    idramo = serializers.UUIDField()


class ItemCPSerializer(ItemWithRamoSerializer):
    genera_prima = serializers.BooleanField(required=False, default=False)


class ItemAnnexSerializer(ItemWithRamoSerializer):
    genera_prima = serializers.BooleanField(required=False, default=False)
    tipo = serializers.CharField(
        max_length=64, required=False, allow_blank=True, allow_null=True
    )


class ItemFormatSerializer(ItemBaseSerializer):
    tipo = serializers.CharField(max_length=64)


class LinkSerializer(serializers.Serializer):
    estado = serializers.CharField(max_length=32, required=False, default="VIGENTE")
    vigencia_desde = serializers.DateField(required=False, allow_null=True)
    vigencia_hasta = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        d = attrs.get("vigencia_desde")
        h = attrs.get("vigencia_hasta")
        if d and h and h < d:
            raise serializers.ValidationError(
                "vigencia_hasta no puede ser menor a vigencia_desde"
            )
        return attrs


class AttachDocBaseSerializer(serializers.Serializer):
    version_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    document = DocPayloadSerializer()
    link = LinkSerializer()


class AttachDocCGSerializer(AttachDocBaseSerializer):
    item = ItemWithRamoSerializer()


class AttachDocCPSerializer(AttachDocBaseSerializer):
    item = ItemCPSerializer()


class AttachDocAnnexSerializer(AttachDocBaseSerializer):
    item = ItemAnnexSerializer()


class AttachDocFormatSerializer(AttachDocBaseSerializer):
    item = ItemFormatSerializer()


# ---------- RA ----------
class RAInputSerializer(serializers.Serializer):
    idmoneda = serializers.UUIDField()
    idtabla_mortalidad = serializers.UUIDField()
    idtipo_estudio = serializers.UUIDField()
    ga = serializers.DecimalField(max_digits=10, decimal_places=6)
    it = serializers.DecimalField(max_digits=10, decimal_places=6)
    utilidad_lim = serializers.DecimalField(max_digits=10, decimal_places=6)
    tarifa_inmediata = serializers.BooleanField()
    vigencia_desde = serializers.DateField(required=False, allow_null=True)
    vigencia_hasta = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        d = attrs.get("vigencia_desde")
        h = attrs.get("vigencia_hasta")
        if d and h and h < d:
            raise serializers.ValidationError(
                "vigencia_hasta no puede ser menor a vigencia_desde"
            )
        return attrs


class RACreateSerializer(serializers.Serializer):
    version_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    ra = RAInputSerializer()
    enlaces = serializers.DictField(
        child=serializers.ListField(child=serializers.UUIDField()), required=False
    )


# ---------- VALIDATE / SUBMIT / STATUS ----------
class ValidateSerializer(serializers.Serializer):
    version_id = serializers.UUIDField()


class SubmitSerializer(serializers.Serializer):
    version_id = serializers.UUIDField()
    vigencia_desde = serializers.DateField()
    vigencia_hasta = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        d = attrs["vigencia_desde"]
        h = attrs.get("vigencia_hasta")
        if h and h < d:
            raise serializers.ValidationError(
                "vigencia_hasta no puede ser menor a vigencia_desde"
            )
        return attrs
