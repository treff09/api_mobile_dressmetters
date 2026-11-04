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

from .views_suivi import (EtapeCommandeView, EssayageCommandeView, PaiementsCommandeView, SupprimerPaiementView,
                          RelancerPaiementView, AvisCommandeView, AvisCouturierListView, TableauDeBordView,
                          AppareilPushView, ParrainageView)

urlpatterns = [
    # Suivi : étapes, essayage, paiements, avis, tableau de bord, push, parrainage
    path('<int:pk>/etape/', EtapeCommandeView.as_view(), name='commande-etape'),
    path('<int:pk>/essayage/', EssayageCommandeView.as_view(), name='commande-essayage'),
    path('<int:pk>/paiements/', PaiementsCommandeView.as_view(), name='commande-paiements'),
    path('<int:pk>/paiements/<int:paiement_id>/', SupprimerPaiementView.as_view(), name='commande-paiement-suppr'),
    path('<int:pk>/relancer/', RelancerPaiementView.as_view(), name='commande-relancer'),
    path('<int:pk>/avis/', AvisCommandeView.as_view(), name='commande-avis'),
    path('couturiers/<int:pro_id>/avis/', AvisCouturierListView.as_view(), name='avis-couturier'),
    path('tableau-de-bord/', TableauDeBordView.as_view(), name='tableau-de-bord'),
    path('appareils/', AppareilPushView.as_view(), name='appareils-push'),
    path('parrainage/', ParrainageView.as_view(), name='parrainage'),
    path('add/', CommandeCreateView.as_view(), name='create-commande'),
    path('pro/', CommandeListByProfessionalView.as_view(), name='professional-orders'),
    path('client/', CommandeListByClientView.as_view(), name='client-orders'),
    path('update-status/<int:pk>/', CommandeUpdateStatusView.as_view(), name='update-commande-status'),
    path('<int:pk>/choisir-paiement/', CommandeChoisirPaiementView.as_view(), name='choisir-paiement-commande'),
    path('<int:pk>/definir-montant/', CommandeDefinirMontantView.as_view(), name='definir-montant-commande'),
    # ── NOUVEAU : upload photo tissu ──────────────────────────
    path('<int:commande_pk>/articles/<int:article_pk>/upload-tissu/', UploadTissuImageView.as_view(), name='upload-tissu'),
]
