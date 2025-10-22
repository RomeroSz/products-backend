from django.urls import path
from catalog.api.views.public import CatalogItemsListView

urlpatterns = [
    path("catalog/items/", CatalogItemsListView.as_view(), name="catalog-items-list"),
]
