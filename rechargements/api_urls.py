from django.urls import path

from .views import ActiverAbonnementView, SubscriptionStatusView
from .views_chariow import chariow_pulse, chariow_retour

# Routes API JWT, utilisées par l'application mobile Flutter.
# Le paiement n'a PAS lieu dans l'application : il se fait sur le site web.
urlpatterns = [
    path('status/', SubscriptionStatusView.as_view(), name='subscription-status'),
    path('activate/', ActiverAbonnementView.as_view(), name='activate-subscription'),  # désactivée (410)
    # --- Chariow ---
    path('chariow/pulse/', chariow_pulse, name='chariow-pulse'),      # URL à déclarer dans Chariow (Pulses)
    path('chariow/retour/', chariow_retour, name='chariow-retour'),   # page de secours après paiement
]
