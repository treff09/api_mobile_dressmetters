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
from core.models import QRToken, ModeleDisponible, MesureClient, quota_commandes
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
        
        # Lien que le client scannera : dans l'appli (scanner) OU avec l'appareil photo du
        # téléphone (ouvre l'appli si installée, sinon propose de la télécharger)
        qr_url = lien_couturier(request, qr_token.token)

        qr_image = qrcode_lib.make(qr_url)
        
        buffer = BytesIO()
        qr_image.save(buffer, format='PNG')
        buffer.seek(0)

        return FileResponse(buffer, content_type='image/png')

# ============================================================
# ACCÈS VIA LE SCAN DU QR CODE
# ============================================================

def _nettoyer_codes_expires(pro):
    from datetime import timedelta
    from django.db.models import Q
    from django.utils import timezone
    limite = timezone.now() - timedelta(minutes=10)
    QRToken.objects.filter(professional_profile=pro, permanent=False).filter(
        Q(premier_scan_le__lt=limite) | Q(premier_scan_le__isnull=True, created_at__lt=limite)).delete()


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
        
        # Couturier qui a désactivé ou supprimé son compte : plus visible
        if not professional_profile.user.is_active:
            return Response({"detail": "Ce couturier n'est plus disponible."}, status=status.HTTP_404_NOT_FOUND)

        # 3. Modèles EN LIGNE du couturier, limités s'il n'a pas (ou plus) d'abonnement actif
        from core.models import modeles_visibles
        modeles = modeles_visibles(professional_profile)
        modeles_serializer = ModeleDisponibleSerializer(modeles, many=True)
        
        # 4. Récupère les mesures DYNAMIQUES du client (s'il est connecté)
        mesures_data = []
        if request.user.is_authenticated and hasattr(request.user, 'client_profile'):
            # On récupère toutes les mesures (EAV) du client
            mesures = MesureClient.objects.filter(client_profile=request.user.client_profile)
            mesures_data = MesureClientSerializer(mesures, many=True).data
                
        # 5. Le QR reste valable 5 minutes après le PREMIER scan : si le client sort de l'écran
        #    par erreur, il peut rescanner sans que le couturier régénère un code.
        qr_token.marquer_scan()
        # Ménage : codes expirés de ce couturier (non permanents)
        _nettoyer_codes_expires(professional_profile)

        return Response({
            "couturier": {
                "id": professional_profile.id,
                "nom_entreprise": professional_profile.nom_entreprise,
                "nom": professional_profile.nom,
                "prenom": professional_profile.prenom,
                "telephone": professional_profile.numero_telephone,
                "accepte_commandes": not quota_commandes(professional_profile)['atteinte'],
            },
            "modeles_disponibles": modeles_serializer.data,
            "mesures_du_client_qui_scanne": mesures_data # Données dynamiques
        }, status=status.HTTP_200_OK)

# ============================================================
# LIEN DE PARTAGE (WhatsApp, statut…)
# ============================================================
# Un QR affiché en boutique expire vite (5 min). Pour WhatsApp, le couturier
# partage un LIEN PERMANENT : https://<site>/c/<code>/
#  • appli installée  → le lien ouvre directement ses modèles dans l'appli ;
#  • appli absente    → la page web propose de la télécharger (selon Android / iPhone).

import os
from urllib.parse import quote

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

PACKAGE_ANDROID = "com.trefftechnologies.dressmatter"
LIEN_PLAY_STORE = f"https://play.google.com/store/apps/details?id={PACKAGE_ANDROID}"


def _base_site(request):
    base = os.getenv("SITE_URL", "").strip().rstrip("/")
    return base or request.build_absolute_uri("/").rstrip("/")


def lien_couturier(request, token):
    return f"{_base_site(request)}/c/{token}/"


class LienPartageView(APIView):
    """GET → {lien, code, qr_png_base64}. ?nouveau=1 désactive l'ancien lien et en crée un autre."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import base64
        pro = getattr(request.user, 'professional_profile', None)
        if pro is None:
            return Response({"detail": "Réservé aux couturiers."}, status=status.HTTP_403_FORBIDDEN)
        if request.query_params.get('nouveau') == '1':
            QRToken.objects.filter(professional_profile=pro, permanent=True).delete()
        qr = QRToken.objects.filter(professional_profile=pro, permanent=True).first()
        if qr is None:
            qr = QRToken.objects.create(professional_profile=pro, token=shortuuid.uuid(), permanent=True)
        lien = lien_couturier(request, qr.token)
        buffer = BytesIO()
        qrcode_lib.make(lien).save(buffer, format='PNG')
        return Response({
            "lien": lien,
            "code": qr.token,
            "qr_png_base64": base64.b64encode(buffer.getvalue()).decode(),
        })


@never_cache
def ouvrir_lien_couturier(request, token):
    """Page ouverte quand on touche le lien hors de l'appli (ou sans l'appli)."""
    qr = QRToken.objects.filter(token=token).select_related('professional_profile__user').first()
    valide = bool(qr and qr.is_valid() and qr.professional_profile.user.is_active)
    pro = qr.professional_profile if valide else None
    lien_appli = f"dressmatter://c/{token}"
    intent_android = (
        f"intent://c/{token}#Intent;scheme=dressmatter;package={PACKAGE_ANDROID};"
        f"S.browser_fallback_url={quote(LIEN_PLAY_STORE, safe='')};end"
    )
    return render(request, 'qr_code/ouvrir_lien.html', {
        "valide": valide,
        "nom": (pro.nom_entreprise or f"{pro.prenom} {pro.nom}".strip()) if pro else "",
        "token": token,
        "lien_appli": lien_appli,
        "intent_android": intent_android,
        "play_store": LIEN_PLAY_STORE,
        "app_store": os.getenv("APP_STORE_URL", "").strip(),
    })


def assetlinks(request):
    """Android App Links : le lien https s'ouvre dans l'appli sans passer par le navigateur.
    Mettre dans le .env : ANDROID_SHA256=AA:BB:…  (Play Console > Intégrité de l'appli >
    Signature d'application > empreinte SHA-256). Plusieurs empreintes séparées par des virgules."""
    empreintes = [e.strip() for e in os.getenv("ANDROID_SHA256", "").split(",") if e.strip()]
    data = [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {"namespace": "android_app", "package_name": PACKAGE_ANDROID,
                   "sha256_cert_fingerprints": empreintes},
    }] if empreintes else []
    return JsonResponse(data, safe=False)
