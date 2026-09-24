from django.urls import path
from .views import ClientMesureView, LibelleMesureDetailView, LibelleMesureListView

urlpatterns = [
    # 1. Pour Flutter : Récupérer les points du gabarit (Nom, X, Y, Catégorie)
    # Endpoint : GET /api/v1/core/points-gabarit/
    path('points-gabarit/', LibelleMesureListView.as_view(), name='points-gabarit'),

    path('points-gabarit/<int:pk>/', LibelleMesureDetailView.as_view(), name='point-detail'),
    path('mesure/', ClientMesureView.as_view(), name='client-mesure-detail'),
]