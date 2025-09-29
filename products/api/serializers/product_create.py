from rest_framework import serializers


class RamoInSerializer(serializers.Serializer):
    idramo = serializers.UUIDField()
    is_principal = serializers.BooleanField(default=False)


class ProductCreateSerializer(serializers.Serializer):
    producto = serializers.DictField(child=serializers.CharField(), allow_empty=False)
    version = serializers.DictField(allow_empty=False)
    modalidades = serializers.ListField(child=serializers.UUIDField(), required=False)
    monedas = serializers.ListField(child=serializers.UUIDField(), required=False)
    ramos = serializers.ListField(child=RamoInSerializer(), required=False)
    geo = serializers.ListField(child=serializers.UUIDField(), required=False)
    tags = serializers.ListField(child=serializers.UUIDField(), required=False)

    def to_input(self):
        p = self.validated_data["producto"]
        v = self.validated_data["version"]
        return dict(
            nombre=p["nombre"],
            estado=p.get("estado", "BORRADOR"),
            tvpo=v.get("tvpo"),
            vigencia_desde=v.get("vigencia_desde"),
            vigencia_hasta=v.get("vigencia_hasta"),
            modalidades=self.validated_data.get("modalidades", []),
            monedas=self.validated_data.get("monedas", []),
            ramos=self.validated_data.get("ramos", []),
            geo=self.validated_data.get("geo", []),
            tags=self.validated_data.get("tags", []),
        )
