from django.urls import path

from products.api.views.product_create import ProductCreateView
from products.api.views.version_lifecycle import (VersionPublishView,
                                                  VersionValidateView)

urlpatterns = [
    path("products/", ProductCreateView.as_view(), name="product-create"),
    path(
        "versions/<uuid:vp_id>/validate",
        VersionValidateView.as_view(),
        name="vp-validate",
    ),
    path(
        "versions/<uuid:vp_id>/publish", VersionPublishView.as_view(), name="vp-publish"
    ),
]
