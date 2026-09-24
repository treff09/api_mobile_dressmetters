from django.urls import path, include
from rest_framework.routers import DefaultRouter


from .views import (
    # ViewSets (pour le router)
    TypeVetementViewSet, 
    MesureClientViewSet,       # <-- Changé (anciennement MesureViewSet)
    AbonnementViewSet, 
    CommandeViewSet, 
    ModeleCommandeViewSet,
    LibelleMesureViewSet,      # Ajouté pour gérer les points de mesure

    # APIViews (pour urlpatterns)
    ModeleListAPIView, 
    ModeleCreateAPIView, 
    ModeleDetailAPIView, 
    ModeleUpdateAPIView, 
    ModeleDestroyAPIView,
    TypeVetementListAPIView,
    OffreAbonnementListView,
    cgu_view,
    check_app_status,
    privacy_policy_view
)

router = DefaultRouter()
router.register(r'type-vetements', TypeVetementViewSet)
router.register(r'mesures-dynamiques', MesureClientViewSet) # Nouveau nom pour tes mesures 0.0
router.register(r'abonnements', AbonnementViewSet)
router.register(r'commandes', CommandeViewSet)
router.register(r'modele-commandes', ModeleCommandeViewSet)
router.register(r'libelles-mesures', LibelleMesureViewSet)

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),

    # --- Gestion des Modèles Disponibles ---
    path('modeles/', ModeleListAPIView.as_view(), name='modele-list'),
    path('modeles/add/', ModeleCreateAPIView.as_view(), name='modele-add'),
    path('modeles/<int:id>/', ModeleDetailAPIView.as_view(), name='modele-detail'),
    path('modeles/<int:id>/update/', ModeleUpdateAPIView.as_view(), name='modele-update'),
    path('modeles/<int:id>/delete/', ModeleDestroyAPIView.as_view(), name='modele-delete'),

    # --- Autres Endpoints ---
    path('type-vetements-list/', TypeVetementListAPIView.as_view(), name='type-vetement-list'),
    path('subscriptions/offers/', OffreAbonnementListView.as_view(), name='offres-abonnement'),
    path('app-status/', check_app_status, name='check_app_status'),

    path('privacy-policy/', privacy_policy_view, name='privacy_policy'),
    path('cgu/', cgu_view, name='cgu'),


]