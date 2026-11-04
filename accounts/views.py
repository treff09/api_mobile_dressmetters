import os

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from django.contrib.auth.models import User

# Importations depuis CORE
# Note: 'Mesure' est supprimé car il n'existe plus dans tes modèles
from core.models import ClientProfile, ProfessionalProfile

from .serializers import (
    ClientRegistrationSerializer, 
    ProfessionalRegistrationSerializer, 
    LoginSerializer,
    ProfessionalProfileSerializer,
    ClientProfileSerializer,
    ChangePasswordSerializer
)

# ============================================================
# INSCRIPTION DES UTILISATEURS
# ============================================================
import random
import logging
from email.utils import formataddr
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

logger = logging.getLogger(__name__)

def send_stylized_otp_email(target_email, otp_code):
    """
    E-mail du code de vérification, écrit pour ne pas finir en spam :
    nom d'expéditeur = la marque, texte brut complet + HTML propre, pas de majuscules partout,
    adresse de réponse. (Le plus important reste le DNS du domaine : SPF, DKIM, DMARC.)
    """
    import datetime
    subject = f"Votre code Dress'Matter : {otp_code}"
    full_sender = formataddr(("Dress'Matter", settings.EMAIL_HOST_USER))
    annee = datetime.date.today().year

    text_content = (
        f"Bonjour,\n\n"
        f"Votre code de vérification Dress'Matter est : {otp_code}\n\n"
        f"Il est valable 15 minutes. Si vous n'avez pas demandé ce code, ignorez simplement cet e-mail.\n\n"
        f"L'équipe Dress'Matter\n"
        f"TREFF COMMUNICATION, Abidjan - aide@treffcommunication.tech\n"
    )

    html_content = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Votre code Dress'Matter</title></head>
<body style="margin:0;padding:24px 12px;background:#f5f3ef;font-family:Arial,Helvetica,sans-serif;color:#222">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:12px">
    <tr><td style="padding:28px 28px 8px;text-align:center">
      <p style="margin:0;font-size:22px;font-weight:bold;color:#0F1B33">Dress'Matter</p>
    </td></tr>
    <tr><td style="padding:8px 28px 0;text-align:center">
      <p style="font-size:16px;line-height:1.5;margin:16px 0">Bonjour,<br>voici votre code de vérification :</p>
      <p style="font-size:34px;font-weight:bold;letter-spacing:8px;color:#C2185B;margin:20px 0">{otp_code}</p>
      <p style="font-size:14px;color:#666;line-height:1.5;margin:0 0 24px">Il est valable 15 minutes.<br>
      Si vous n'avez pas demandé ce code, ignorez simplement cet e-mail.</p>
    </td></tr>
    <tr><td style="padding:16px 28px 24px;text-align:center;border-top:1px solid #eee">
      <p style="margin:0;font-size:12px;color:#888">&copy; {annee} TREFF COMMUNICATION, Abidjan<br>
      Besoin d'aide ? aide@treffcommunication.tech</p>
    </td></tr>
  </table>
</body></html>"""

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=full_sender,
        to=[target_email],
        reply_to=["aide@treffcommunication.tech"],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)

class ClientRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        otp_input = request.data.get('otp')
        user_data = request.data.get('user', {})
        email = user_data.get('email')

        if not email:
            return Response({"message": "L'adresse e-mail est requise."}, status=status.HTTP_400_BAD_REQUEST)

        if otp_input:
            cache_key = f"otp_reg_{email}"
            cached_data = cache.get(cache_key)
            if not cached_data or str(cached_data['otp']) != str(otp_input):
                return Response({"message": "Code OTP incorrect ou expiré."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = ClientRegistrationSerializer(data=cached_data['data'])
            if serializer.is_valid():
                serializer.save()
                cache.delete(cache_key)
                return Response({"message": "Inscription réussie !"}, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer = ClientRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            otp = str(random.randint(100000, 999999))
            cache.set(f"otp_reg_{email}", {"otp": otp, "data": request.data}, timeout=900)
            
            try:
                send_stylized_otp_email(email, otp)
                return Response({"message": "Un code OTP a été envoyé.", "step": "otp_sent"}, status=status.HTTP_200_OK)
            except Exception as e:
                logger.error(f"Erreur envoi email : {str(e)}")
                return Response({"message": "Erreur lors de l'envoi de l'e-mail."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProfessionalRegistrationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        otp_input = request.data.get('otp')
        user_data = request.data.get('user', {})
        email = user_data.get('email')

        if not email:
            return Response({"message": "Email requis."}, status=status.HTTP_400_BAD_REQUEST)

        if otp_input:
            cache_key = f"otp_reg_{email}"
            cached_data = cache.get(cache_key)
            if not cached_data or str(cached_data['otp']) != str(otp_input):
                return Response({"message": "OTP incorrect ou expiré."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = ProfessionalRegistrationSerializer(data=cached_data['data'])
            if serializer.is_valid():
                serializer.save()
                cache.delete(cache_key)
                return Response({'message': 'Succès !'}, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer = ProfessionalRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            otp = str(random.randint(100000, 999999))
            cache.set(f"otp_reg_{email}", {"otp": otp, "data": request.data}, timeout=900)

            try:
                send_stylized_otp_email(email, otp)
                return Response({"message": "OTP envoyé.", "step": "otp_sent"}, status=status.HTTP_200_OK)
            except Exception as e:
                logger.error(f"Erreur SMTP Pro : {str(e)}")
                return Response({"message": "Erreur e-mail."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
# ============================================================
# AUTHENTIFICATION & SESSION
# ============================================================

def _reponse_connexion(user):
    """Réponse de connexion (tokens + infos) : utilisée par la connexion et la réactivation."""
    refresh = RefreshToken.for_user(user)
    profile_type = 'professionnel' if hasattr(user, 'professional_profile') else 'client'
    return Response({
        'status': status.HTTP_200_OK,
        'data': {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user_info': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'profile_type': profile_type,
            }
        }
    }, status=status.HTTP_200_OK)


def _compte_en_pause(email, password):
    """
    Si l'e-mail et le mot de passe sont bons mais que le compte a été désactivé
    ou supprimé (et reste récupérable), renvoie (user, depart). Sinon (None, None).
    """
    from core.models import DepartCompte
    user = User.objects.filter(email__iexact=(email or '').strip()).first()
    if not user or user.is_active or not user.check_password(password or ''):
        return None, None
    depart = DepartCompte.en_cours_pour(user)
    if not depart:
        return None, None
    if depart.action == DepartCompte.SUPPRESSION and depart.date_limite and timezone.now() > depart.date_limite:
        return None, None  # délai de récupération dépassé : plus récupérable
    return user, depart


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Compte désactivé ou supprimé (récupérable) : on propose de le récupérer
        user, depart = _compte_en_pause(request.data.get('email'), request.data.get('password'))
        if user:
            supprime = depart.action == depart.SUPPRESSION
            return Response({
                'code': 'COMPTE_SUPPRIME' if supprime else 'COMPTE_DESACTIVE',
                'date': depart.date_demande.strftime('%d/%m/%Y'),
                'date_limite': depart.date_limite.strftime('%d/%m/%Y') if supprime else None,
                'message': (f"Ce compte a été supprimé le {depart.date_demande:%d/%m/%Y}. "
                            f"Tu peux encore le récupérer jusqu'au {depart.date_limite:%d/%m/%Y}.")
                           if supprime else
                           f"Ton compte est en pause depuis le {depart.date_demande:%d/%m/%Y}.",
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            return _reponse_connexion(serializer.validated_data['user'])

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MotifsDepartView(APIView):
    """GET /api/v1/accounts/motifs-depart/ : motifs proposés + délai de récupération (réglés dans l'admin)."""
    permission_classes = [AllowAny]

    def get(self, request):
        from core.models import MotifDepart, AppConfiguration
        return Response({
            'delai_recuperation_jours': AppConfiguration.delai_recuperation(),
            'motifs': [
                {'id': m.id, 'libelle': m.libelle, 'demande_precision': m.demande_precision}
                for m in MotifDepart.objects.filter(actif=True)
            ],
        })


class DepartCompteView(APIView):
    """
    POST /api/v1/accounts/depart/
    {"action": "DESACTIVATION" | "SUPPRESSION", "motif_id": 3, "precision": "..."}
    Dans les deux cas le compte est désactivé (réversible) et toutes les sessions sont fermées.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.models import DepartCompte, MotifDepart
        action = request.data.get('action')
        if action not in (DepartCompte.DESACTIVATION, DepartCompte.SUPPRESSION):
            return Response({'error': 'Action inconnue.'}, status=status.HTTP_400_BAD_REQUEST)
        motif = MotifDepart.objects.filter(id=request.data.get('motif_id'), actif=True).first()
        if not motif:
            return Response({'error': 'Choisis un motif.'}, status=status.HTTP_400_BAD_REQUEST)
        precision = (request.data.get('precision') or '').strip()
        if motif.demande_precision and not precision:
            return Response({'error': 'Écris ton motif.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        depart = DepartCompte.objects.create(user=user, action=action, motif=motif, precision=precision[:1000])
        user.is_active = False
        user.save(update_fields=['is_active'])
        # Ferme toutes les sessions ouvertes (sur tous les téléphones)
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

        if action == DepartCompte.SUPPRESSION:
            msg = (f"Ton compte est supprimé. Tu peux encore le récupérer jusqu'au "
                   f"{depart.date_limite:%d/%m/%Y} en te reconnectant.")
        else:
            msg = "Ton compte est en pause. Reconnecte-toi quand tu veux pour le réactiver."
        return Response({'message': msg}, status=status.HTTP_200_OK)


class ReactiverCompteView(APIView):
    """POST /api/v1/accounts/reactiver/ {"email", "password"} : récupère le compte et connecte."""
    permission_classes = [AllowAny]

    def post(self, request):
        user, depart = _compte_en_pause(request.data.get('email'), request.data.get('password'))
        if not user:
            return Response({'error': "Impossible de récupérer ce compte."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = True
        user.save(update_fields=['is_active'])
        depart.date_reactivation = timezone.now()
        depart.save(update_fields=['date_reactivation'])
        return _reponse_connexion(user)


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

class LogoutView(APIView):
    """
    Déconnecte l'utilisateur en invalidant TOUS ses tokens de session.
    L'utilisateur doit être authentifié via son Bearer Token dans le Header.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # On récupère tous les tokens "outstanding" (en cours) de l'utilisateur
            tokens = OutstandingToken.objects.filter(user=request.user)
            
            # On les ajoute tous à la liste noire
            for token in tokens:
                # On vérifie si le token n'est pas déjà blacklisté pour éviter les erreurs
                BlacklistedToken.objects.get_or_create(token=token)
            
            return Response(
                {"detail": "Déconnexion réussie. Tous les tokens de session ont été révoqués."}, 
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"detail": "Une erreur est survenue lors de la déconnexion."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
# ============================================================
# GESTION DES INFORMATIONS PERSONNELLES
# ============================================================

class PersonalInfoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if hasattr(user, 'professional_profile'):
            serializer = ProfessionalProfileSerializer(user.professional_profile)
            role = "pro"
        elif hasattr(user, 'client_profile'):
            serializer = ClientProfileSerializer(user.client_profile)
            role = "client"
        else:
            return Response({"error": "Profil introuvable"}, status=status.HTTP_404_NOT_FOUND)

        return Response({"role": role, "data": serializer.data})

    def put(self, request):
        user = request.user
        profile = None
        
        if hasattr(user, 'professional_profile'):
            profile = user.professional_profile
            serializer = ProfessionalProfileSerializer(profile, data=request.data, partial=True)
        elif hasattr(user, 'client_profile'):
            profile = user.client_profile
            serializer = ClientProfileSerializer(profile, data=request.data, partial=True)
        
        if profile and serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors or {"error": "Profil introuvable"}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['ancien_mot_de_passe']):
                return Response({"error": "Ancien mot de passe incorrect"}, status=status.HTTP_400_BAD_REQUEST)

            user.set_password(serializer.validated_data['nouveau_mot_de_passe'])
            user.save()
            return Response({"message": "Mot de passe modifié avec succès"})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


import random
import logging
from email.utils import formataddr
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

logger = logging.getLogger(__name__)

def send_password_reset_otp(target_email, otp_code):
    """Code de récupération du mot de passe (même e-mail propre que l'inscription)."""
    send_stylized_otp_email(target_email, otp_code)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        step = request.data.get('step') # 'send_email', 'verify_otp', 'reset_password'
        email = request.data.get('email')

        if not email:
            return Response({"message": "L'email est requis."}, status=status.HTTP_400_BAD_REQUEST)

        # --- ÉTAPE 1 : ENVOI DE L'EMAIL ---
        if step == 'send_email':
            try:
                user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
                if not user:
                    raise User.DoesNotExist
                otp = str(random.randint(1000, 9999)) # 4 chiffres comme dans ton Flutter
                
                # Stockage en cache (validité 10 min)
                cache.set(f"password_reset_{email}", {"otp": otp, "verified": False}, timeout=600)
                
                send_password_reset_otp(email, otp)
                return Response({"message": "Code envoyé !"}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                return Response({"message": "Aucun compte trouvé avec cet email."}, status=status.HTTP_404_NOT_FOUND)

        # --- ÉTAPE 2 : VÉRIFICATION DE L'OTP ---
        elif step == 'verify_otp':
            otp_input = request.data.get('otp')
            cached_data = cache.get(f"password_reset_{email}")

            if cached_data and str(cached_data['otp']) == str(otp_input):
                # On marque comme vérifié dans le cache pour autoriser l'étape 3
                cache.set(f"password_reset_{email}", {"otp": otp_input, "verified": True}, timeout=600)
                return Response({"message": "Code valide."}, status=status.HTTP_200_OK)
            
            return Response({"message": "Code incorrect ou expiré."}, status=status.HTTP_400_BAD_REQUEST)

        # --- ÉTAPE 3 : RÉINITIALISATION DU MOT DE PASSE ---
        elif step == 'reset_password':
            new_password = request.data.get('password')
            cached_data = cache.get(f"password_reset_{email}")

            if not cached_data or not cached_data.get('verified'):
                return Response({"message": "Action non autorisée. Veuillez vérifier l'OTP d'abord."}, status=status.HTTP_403_FORBIDDEN)

            try:
                user = User.objects.filter(email__iexact=email.strip()).first()
                if not user:
                    raise User.DoesNotExist
                user.set_password(new_password)
                user.save()
                
                # Supprimer le cache après succès
                cache.delete(f"password_reset_{email}")
                return Response({"message": "Mot de passe modifié avec succès !"}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"message": "Une erreur est survenue."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"message": "Étape invalide."}, status=status.HTTP_400_BAD_REQUEST)