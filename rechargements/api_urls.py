from django.urls import path
from .views import ActiverAbonnementView, SubscriptionStatusView

# Routes API JWT, utilisées par l'application mobile Flutter.
urlpatterns = [
    path('status/', SubscriptionStatusView.as_view(), name='subscription-status'),
    path('activate/', ActiverAbonnementView.as_view(), name='activate-subscription'),
]
