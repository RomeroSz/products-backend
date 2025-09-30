from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from common.application.db import set_db_context_from_request
from products.api.serializers.validate_and_publish import publish_version, validate_version
from products.api.serializers.wizard import ValidateSerializer, SubmitSerializer


class WizardValidateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id: str):
        set_db_context_from_request(request)
        s = ValidateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        res = validate_version(str(s.validated_data["version_id"]))
        if not res.ok:
            return Response({"ok": False, "message": res.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True}, status=status.HTTP_200_OK)


class WizardSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id: str):
        set_db_context_from_request(request)
        s = SubmitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        res = publish_version(
            str(v["version_id"]),
            str(v["vigencia_desde"]),
            str(v.get("vigencia_hasta")) if v.get("vigencia_hasta") else None
        )
        return Response({"ok": res.ok, "version_id": res.version_id}, status=status.HTTP_200_OK)
