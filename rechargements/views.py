from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.models import Abonnement, OffreAbonnement


class ActiverAbonnementView(APIView):
    """
    Active (ou prolonge) l'abonnement du professionnel connecté pour l'offre
    choisie. Aucun wallet/point n'intervient : le règlement réel se fait
    hors-app (Mobile Money à intégrer plus tard) ; pour l'instant
    l'activation se fait directement, comme validation manuelle du paiement.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Fermée : cette route activait l'abonnement SANS paiement. L'activation se fait
        # désormais uniquement à la réception du Pulse Chariow « successful.sale ».
        return Response({'error': "Utilise le paiement en ligne pour activer ton abonnement."},
                        status=status.HTTP_410_GONE)


class SubscriptionStatusView(APIView):
    """
    Statut d'abonnement du professionnel connecté : actif ou non, date de
    fin, jours restants. Aucun solde/point n'est renvoyé : le wallet n'existe
    plus dans l'application.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        data = {
            "username": user.username,
            "is_professional": hasattr(user, 'professional_profile'),
        }

        if hasattr(user, 'professional_profile'):
            pro = user.professional_profile
            abonnement = getattr(pro, 'abonnement', None)
            data["entreprise"] = pro.nom_entreprise
            data["abonnement_actif"] = abonnement.est_actif if abonnement else False
            data["date_fin_abonnement"] = abonnement.date_fin if abonnement else None
            data["jours_restants"] = abonnement.jours_restants if abonnement else None
            # Limite de modèles sans abonnement (réglable dans l'admin)
            from core.models import AppConfiguration, ModeleDisponible
            data["limite_modeles_gratuits"] = AppConfiguration.limite_modeles_gratuits()
            data["nb_modeles"] = ModeleDisponible.objects.filter(professional_profile=pro, actif=True).count()
            data["limite_retraits_gratuits"] = AppConfiguration.limite_retraits_gratuits()
            data["nb_retraits"] = pro.nb_retraits

        return Response(data, status=status.HTTP_200_OK)
