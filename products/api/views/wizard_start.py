from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from common.application.db import set_db_context_from_request
from products.api.serializers.wizard import WizardStartSerializer
from products.application.use_cases.wizard_start import wizard_start


class WizardStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        set_db_context_from_request(request)
        s = WizardStartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        res = wizard_start(**s.validated_data)
        return Response({
            "product_id": res.product_id,
            "version_id": res.version_id,
            "case_id": res.case_id,
            "product_case_id": res.product_case_id,
        }, status=status.HTTP_201_CREATED)
