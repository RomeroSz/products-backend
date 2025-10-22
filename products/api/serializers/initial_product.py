from rest_framework import serializers


class FileRefSer(serializers.Serializer):
    nombre = serializers.CharField()
    url = serializers.URLField()


class ProductSer(serializers.Serializer):
    company_id = serializers.UUIDField()
    nombre_tecnico = serializers.CharField()
    nombre_comercial = serializers.CharField()


class RamoPathSer(serializers.Serializer):
    pathIds = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False, min_length=1
    )


class CGSer(serializers.Serializer):
    uniform = serializers.BooleanField()
    referencia_normativa = serializers.CharField(
        allow_blank=True, required=False)
    file = FileRefSer(allow_null=True, required=False)


class CPItemSer(serializers.Serializer):
    key = serializers.CharField()
    nombre = serializers.CharField()
    file = FileRefSer()
    # soporte opcional de ramo por compatibilidad con tu payload actual
    ramo = serializers.DictField(required=False)


class AnnexItemSer(serializers.Serializer):
    key = serializers.CharField()
    nombre = serializers.CharField()
    parent_cp = serializers.CharField()
    genera_prima = serializers.BooleanField()
    file = FileRefSer()


class RATargetsSer(serializers.Serializer):
    cp_keys = serializers.ListField(
        child=serializers.CharField(), allow_empty=False)
    annex_keys = serializers.ListField(
        child=serializers.CharField(), required=False)


class RADataSer(serializers.Serializer):
    idmoneda = serializers.UUIDField()
    idtabla_mortalidad = serializers.UUIDField(allow_null=True, required=False)
    idtipo_estudio = serializers.UUIDField()
    ga = serializers.DecimalField(max_digits=6, decimal_places=4)
    it = serializers.DecimalField(max_digits=6, decimal_places=4)
    utilidad_lim = serializers.DecimalField(max_digits=6, decimal_places=4)
    tarifa_inmediata = serializers.BooleanField()
    vigencia_desde = serializers.DateField()
    vigencia_hasta = serializers.DateField(allow_null=True, required=False)
    actuario_cedula = serializers.CharField(required=False, allow_blank=True)


class RAItemSer(serializers.Serializer):
    key = serializers.CharField()
    data = RADataSer()
    targets = RATargetsSer()
    files = serializers.ListField(child=FileRefSer(), allow_empty=False)
    supports = serializers.ListField(child=FileRefSer(), required=False)


class FormatsSer(serializers.Serializer):
    basicos = serializers.DictField()
    otros = serializers.ListField(child=FileRefSer(), required=False)


class InitialProductPayloadSer(serializers.Serializer):
    idempotency_key = serializers.CharField()
    product = ProductSer()
    ramos = serializers.ListField(child=RamoPathSer(), allow_empty=False)
    cg = CGSer()
    cp = serializers.ListField(child=CPItemSer(), allow_empty=True)
    annexes = serializers.ListField(child=AnnexItemSer(), allow_empty=True)
    ra = serializers.ListField(child=RAItemSer(), allow_empty=True)
    formats = FormatsSer()
