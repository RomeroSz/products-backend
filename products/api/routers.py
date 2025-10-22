from django.urls import path
from .views.initial_product import InitialProductCreateAPIView

urlpatterns = [
    path("wizard/products/initial", InitialProductCreateAPIView.as_view(),
         name="wizard-products-initial"),
]
