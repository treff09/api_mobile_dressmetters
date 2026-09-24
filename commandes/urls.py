# commandes/urls.py
from django.urls import path
from .views import (
    CommandeCreateView,
    CommandeListByProfessionalView,
    CommandeListByClientView,
    CommandeUpdateStatusView,
    CommandeChoisirPaiementView,
    CommandeDefinirMontantView,
    UploadTissuImageView,
)

urlpatterns = [
    path('add/', CommandeCreateView.as_view(), name='create-commande'),
    path('pro/', CommandeListByProfessionalView.as_view(), name='professional-orders'),
    path('client/', CommandeListByClientView.as_view(), name='client-orders'),
    path('update-status/<int:pk>/', CommandeUpdateStatusView.as_view(), name='update-commande-status'),
    path('<int:pk>/choisir-paiement/', CommandeChoisirPaiementView.as_view(), name='choisir-paiement-commande'),
    path('<int:pk>/definir-montant/', CommandeDefinirMontantView.as_view(), name='definir-montant-commande'),
    # ── NOUVEAU : upload photo tissu ──────────────────────────
    path('<int:commande_pk>/articles/<int:article_pk>/upload-tissu/', UploadTissuImageView.as_view(), name='upload-tissu'),
]
