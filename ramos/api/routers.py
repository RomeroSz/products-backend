# products-backend/ramos/api/routers.py
from django.urls import path

# Public
from ramos.api.views.public import (
    CommissionCapView,
    IsVidaPathView,
    RamosRootsView,
    RamosChildrenView,
    RamosTreeView,
    RamosValidatePathView,
    RamosModalidadesView,
    RamosContablesView,
)

# Admin · Contable
from ramos.api.views.admin_contable import (
    AdminContableMappingListView,
    AdminContableMappingCreateView,
    AdminContableMappingDeleteView,
    AdminContableMappingBulkView,
    AdminContableAuditUnmappedView,
)

urlpatterns = [
    # --- Público (flujo de creación) ---
    path("ramos/roots/", RamosRootsView.as_view(), name="ramos-roots"),
    path("ramos/children/", RamosChildrenView.as_view(), name="ramos-children"),
    path("ramos/tree/", RamosTreeView.as_view(), name="ramos-tree"),
    
     path("ramos/is-vida/", IsVidaPathView.as_view(), name="ramos-is-vida"),


    path("ramos/validate-path/", RamosValidatePathView.as_view(),
         name="ramos-validate-path"),
    path("ramos/<uuid:node_id>/modalidades/",
         RamosModalidadesView.as_view(), name="ramos-modalidades"),
    path("ramos/<uuid:node_id>/contables/",
         RamosContablesView.as_view(), name="ramos-contables"),

    # --- Admin · Contable (CRUD + auditorías) ---
    path("admin/contable/mapping/", AdminContableMappingListView.as_view(),
         name="admin-contable-mapping-list"),
    path("admin/contable/mapping/create/", AdminContableMappingCreateView.as_view(),
         name="admin-contable-mapping-create"),
    path("admin/contable/mapping/<uuid:rtc_id>/delete/",
         AdminContableMappingDeleteView.as_view(), name="admin-contable-mapping-delete"),
    path("admin/contable/mapping/bulk/", AdminContableMappingBulkView.as_view(),
         name="admin-contable-mapping-bulk"),
    path("admin/contable/audit/unmapped/", AdminContableAuditUnmappedView.as_view(),
         name="admin-contable-audit-unmapped"),
     path('commission/cap/', CommissionCapView.as_view(), name='commission-cap'),
]
