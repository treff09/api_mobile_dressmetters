from django.urls import path
from .views import ClientMesureView, LibelleMesureDetailView, LibelleMesureListView, MesuresRequisesView, BibliothequeMesuresView, PersonnesView, PersonneDetailView

urlpatterns = [
    # 1. Pour Flutter : Récupérer les points du gabarit (Nom, X, Y, Catégorie)
    # Endpoint : GET /api/v1/core/points-gabarit/
    path('points-gabarit/', LibelleMesureListView.as_view(), name='points-gabarit'),

    path('points-gabarit/<int:pk>/', LibelleMesureDetailView.as_view(), name='point-detail'),
    path('mesure/', ClientMesureView.as_view(), name='client-mesure-detail'),
    # Mode guidé : mesures à prendre pour un modèle (?modele=<id>) ou un type (?type=<id>)
    path('mesures-requises/', MesuresRequisesView.as_view(), name='mesures-requises'),
    # Couturier : bibliothèque de mesures + création de ses propres mesures
    path('bibliotheque/', BibliothequeMesuresView.as_view(), name='bibliotheque-mesures'),
    # Personnes suivies par le client (Moi, Junior, Malik…)
    path('personnes/', PersonnesView.as_view(), name='personnes'),
    path('personnes/<int:pk>/', PersonneDetailView.as_view(), name='personne-detail'),
]