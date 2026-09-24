from django.urls import path

from commandes.views import (
    web_login_view,
    web_recharge_view,
    web_payer_abonnement_view,
    web_paiement_attente_view,
    web_confirmer_paiement_view,
)

urlpatterns = [
    path('accounts/web-login/', web_login_view, name='web_login'),
    path('payments/recharge/', web_recharge_view, name='web_recharge'),
    path('payments/payer/<int:offre_id>/', web_payer_abonnement_view, name='web_payer_abonnement'),
    path('payments/attente/<str:order_id>/', web_paiement_attente_view, name='web_paiement_attente'),
    path('payments/confirmer/<str:order_id>/', web_confirmer_paiement_view, name='web_confirmer_paiement'),
]