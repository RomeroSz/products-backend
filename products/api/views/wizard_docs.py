from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from common.application.db import set_db_context_from_request
from products.api.serializers.doc_attach import attach_document_to_version
from products.api.serializers.wizard import (
    AttachDocCGSerializer, AttachDocCPSerializer,
    AttachDocAnnexSerializer, AttachDocFormatSerializer
)


class _BaseAttachView(APIView):
    permission_classes = [IsAuthenticated]
    section = None
    serializer_class = None

    def post(self, request):
        set_db_context_from_request(request)
        s = self.serializer_class(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        res = attach_document_to_version(
            section=self.section,
            product_id=str(v["product_id"]),
            version_id=str(v["version_id"]),
            document=v["document"],
            item=v["item"],
            link=v["link"],
        )
        return Response({
            "link_id": res.link_id,
            "document_id": res.document_id,
            "specific_id": res.specific_id,
            "case_id": res.case_id,
        }, status=status.HTTP_201_CREATED)


class AttachCGView(_BaseAttachView):
    section = "CG"
    serializer_class = AttachDocCGSerializer


class AttachCPView(_BaseAttachView):
    section = "CP"
    serializer_class = AttachDocCPSerializer


class AttachAnnexView(_BaseAttachView):
    section = "ANNEX"
    serializer_class = AttachDocAnnexSerializer


class AttachFormatView(_BaseAttachView):
    section = "FORMAT"
    serializer_class = AttachDocFormatSerializer
