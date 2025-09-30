from django.urls import path
from expediente.api.views.tree import CaseTreeView

urlpatterns = [
    path("expediente/<uuid:product_case_id>/tree",
         CaseTreeView.as_view(), name="case-tree"),
]
