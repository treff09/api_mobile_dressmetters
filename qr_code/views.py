from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from io import BytesIO

import qrcode as qrcode_lib
import shortuuid 

from accounts.permissions import IsProfessionalOrReadOnly
# On importe les nouveaux modèles et serializers
from core.models import QRToken, ModeleDisponible, MesureClient 
from core.serializers import ModeleDisponibleSerializer, MesureClientSerializer

# ============================================================
# GÉNÉRATION DU QR CODE
# ============================================================

class GenerateQRView(APIView):
    permission_classes = [IsAuthenticated, IsProfessionalOrReadOnly]

    def get(self, request):
        if not hasattr(request.user, 'professional_profile'):
            return Response({"detail": "Seuls les professionnels peuvent générer un code QR."},
                            status=status.HTTP_403_FORBIDDEN)

        token_key = shortuuid.uuid()
        qr_token = QRToken.objects.create(
            professional_profile=request.user.professional_profile,
            token=token_key
        )
        
        # URL que le client scannera
        qr_url = request.build_absolute_uri(f'/api/v1/qr/access/{qr_token.token}/')

        qr_image = qrcode_lib.make(qr_url)
        
        buffer = BytesIO()
        qr_image.save(buffer, format='PNG')
        buffer.seek(0)

        return FileResponse(buffer, content_type='image/png')

# ============================================================
# ACCÈS VIA LE SCAN DU QR CODE
# ============================================================

class QRAccessView(APIView):
    def get(self, request, token_key):
        # 1. Vérifie si le token existe et est valide
        qr_token = get_object_or_404(QRToken, token=token_key)
        if not qr_token.is_valid():
            qr_token.delete()
            return Response({"detail": "Ce code QR est expiré ou invalide."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        # 2. Récupère les informations du professionnel
        professional_profile = qr_token.professional_profile
        
        # 3. Récupère les modèles disponibles du couturier
        modeles = ModeleDisponible.objects.filter(professional_profile=professional_profile)
        modeles_serializer = ModeleDisponibleSerializer(modeles, many=True)
        
        # 4. Récupère les mesures DYNAMIQUES du client (s'il est connecté)
        mesures_data = []
        if request.user.is_authenticated and hasattr(request.user, 'client_profile'):
            # On récupère toutes les mesures (EAV) du client
            mesures = MesureClient.objects.filter(client_profile=request.user.client_profile)
            mesures_data = MesureClientSerializer(mesures, many=True).data
                
        # 5. Supprime le token après usage (usage unique pour sécurité)
        qr_token.delete()

        return Response({
            "couturier": {
                "id": professional_profile.id,
                "nom_entreprise": professional_profile.nom_entreprise,
                "nom": professional_profile.nom,
                "prenom": professional_profile.prenom,
                "telephone": professional_profile.numero_telephone
            },
            "modeles_disponibles": modeles_serializer.data,
            "mesures_du_client_qui_scanne": mesures_data # Données dynamiques
        }, status=status.HTTP_200_OK)