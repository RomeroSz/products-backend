from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from common.application.db import set_db_context_from_request
from products.api.serializers.create_ra import create_ra_and_links
from products.api.serializers.wizard import RACreateSerializer


class WizardRAView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        set_db_context_from_request(request)
        s = RACreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        res = create_ra_and_links(
            product_id=str(v["product_id"]),
            version_id=str(v["version_id"]),
            ra=v["ra"],
            enlaces=v.get("enlaces") or {}
        )
        return Response({"ra_id": res.ra_id, "case_id": res.case_id}, status=status.HTTP_201_CREATED)
