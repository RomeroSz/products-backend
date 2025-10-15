# catalog/api/routers.py
from django.urls import path
from .views.catalog_items import (
    CatalogItemsListView,
    CatalogItemByIdView,
    CatalogItemsSearchView,
)

from .views.ramos import (
    RamosTreeView,
    RamosChildrenView,
    RamosValidatePathView,
    RamosResolveCodesView,
    RamosMultiRulesView,
    RamosAllowedModalidadesView,
    ModalidadesListView,
)

urlpatterns = [
    # General (para cualquier tipo de ítem del catálogo)
    path("catalog/items/", CatalogItemsListView.as_view(),
         name="catalog-items-list"),
    path("catalog/items/<uuid:item_id>/",
         CatalogItemByIdView.as_view(), name="catalog-items-by-id"),
    path("catalog/items/search/", CatalogItemsSearchView.as_view(),
         name="catalog-items-search"),
]

urlpatterns += [
    path("catalog/ramos/tree/", RamosTreeView.as_view(), name="catalog-ramos-tree"),
    path("catalog/ramos/children/", RamosChildrenView.as_view(),
         name="catalog-ramos-children"),
    path("catalog/ramos/validate_path/", RamosValidatePathView.as_view(),
         name="catalog-ramos-validate-path"),
    path("catalog/ramos/resolve_codes/", RamosResolveCodesView.as_view(),
         name="catalog-ramos-resolve-codes"),
    path("catalog/ramos/multi_rules/", RamosMultiRulesView.as_view(),
         name="catalog-ramos-multi-rules"),
    path("catalog/ramos/allowed_modalidades/", RamosAllowedModalidadesView.as_view(),
         name="catalog-ramos-allowed-modalidades"),
    path("catalog/modalidades/", ModalidadesListView.as_view(),
         name="catalog-modalidades"),
]
