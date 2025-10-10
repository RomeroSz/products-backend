from django.urls import path

from products.api.views.wizard_docs import (AttachAnnexView, AttachCGView,
                                            AttachCPView, AttachFormatView)
from products.api.views.wizard_paso1 import WizardCreateDraftView
from products.api.views.wizard_ra import WizardRAView
from products.api.views.wizard_start import WizardStartView
from products.api.views.wizard_status import WizardStatusView
from products.api.views.wizard_validate_publish import (WizardSubmitView,
                                                        WizardValidateView)

urlpatterns = [
    path("wizard/products/start", WizardStartView.as_view(), name="wizard-start"),
    path("products/wizard/paso1/create_draft/", WizardCreateDraftView.as_view(), name="products-wizard-paso1-create"),
    path("wizard/docs/cg", AttachCGView.as_view(), name="wizard-docs-cg"),
    path("wizard/docs/cp", AttachCPView.as_view(), name="wizard-docs-cp"),
    path("wizard/docs/annex", AttachAnnexView.as_view(), name="wizard-docs-annex"),
    path("wizard/docs/format", AttachFormatView.as_view(), name="wizard-docs-format"),
    path("wizard/ra", WizardRAView.as_view(), name="wizard-ra"),
    path(
        "wizard/<uuid:case_id>/validate",
        WizardValidateView.as_view(),
        name="wizard-validate",
    ),
    path(
        "wizard/<uuid:case_id>/submit", WizardSubmitView.as_view(), name="wizard-submit"
    ),
    path(
        "wizard/<uuid:case_id>/status", WizardStatusView.as_view(), name="wizard-status"
    ),
]
