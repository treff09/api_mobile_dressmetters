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
        user = request.user
        if not hasattr(user, 'professional_profile'):
            return Response({'error': "Profil professionnel introuvable."}, status=status.HTTP_404_NOT_FOUND)

        pro_profile = user.professional_profile

        offre_id = request.data.get('offre_id')
        if not offre_id:
            return Response({'error': "ID de l'offre manquant."}, status=status.HTTP_400_BAD_REQUEST)

        offre = get_object_or_404(OffreAbonnement, id=offre_id)
        now = timezone.now()

        with transaction.atomic():
            abonnement, created = Abonnement.objects.get_or_create(
                professional_profile=pro_profile,
                defaults={'offre': offre, 'date_fin': now}
            )

            # Si un abonnement est déjà actif, on prolonge à partir de sa date
            # de fin actuelle plutôt que de repartir de zéro.
            if not created and abonnement.date_fin and abonnement.date_fin > now:
                nouvelle_date_fin = abonnement.date_fin + timedelta(days=offre.duree_jours)
            else:
                nouvelle_date_fin = now + timedelta(days=offre.duree_jours)

            abonnement.offre = offre
            abonnement.date_fin = nouvelle_date_fin
            abonnement.save()

        return Response({
            'status': 'success',
            'message': f'Offre {offre.nom} activée',
            'expire_le': nouvelle_date_fin.strftime("%d/%m/%Y"),
            'jours_restants': abonnement.jours_restants,
        }, status=status.HTTP_200_OK)


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

        return Response(data, status=status.HTTP_200_OK)
