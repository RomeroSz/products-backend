# catalog/api/routers.py
from django.urls import path

from .views.catalog_items import (
    CatalogItemsListView,
    CatalogItemByIdView,
    CatalogItemsSearchView,
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
