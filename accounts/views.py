import os

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
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
    Envoie un email HTML stylisé en forçant l'affichage de COUTURIER DIGITAL.
    """
    subject = f"{otp_code} est votre code de vérification"
    
    # On définit explicitement le nom et l'email
    display_name = "COUTURIER DIGITAL"
    sender_email = settings.EMAIL_HOST_USER
    
    # formataddr crée la chaîne "COUTURIER DIGITAL <votre@email.com>"
    full_sender = formataddr((display_name, sender_email))
    
    html_content = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 550px; margin: 0 auto; border: 1px solid #f0f0f0; border-radius: 15px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
        <div style="background-color: #E91E63; padding: 35px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 26px; letter-spacing: 3px; text-transform: uppercase; font-weight: 900;">COUTURIER DIGITAL</h1>
        </div>
        <div style="padding: 40px 30px; text-align: center; background-color: #ffffff;">
            <h2 style="color: #333; margin-top: 0; font-size: 22px;">Vérification de sécurité</h2>
            <p style="color: #555; font-size: 16px; line-height: 1.6;">Pour finaliser votre opération sur <strong>COUTURIER DIGITAL</strong>, veuillez utiliser le code de confirmation suivant :</p>
            
            <div style="margin: 40px 0;">
                <div style="background-color: #FFF0F5; border: 2px solid #E91E63; display: inline-block; padding: 20px 40px; border-radius: 12px;">
                    <span style="font-size: 42px; font-weight: 800; color: #E91E63; letter-spacing: 10px;">{otp_code}</span>
                </div>
            </div>
            
            <p style="color: #888; font-size: 14px; font-style: italic;">Ce code est à usage unique et expire dans 15 minutes.</p>
        </div>
        <div style="background-color: #f9f9f9; padding: 25px; text-align: center; border-top: 1px solid #eeeeee;">
            <p style="margin: 0; font-size: 13px; color: #aaa; letter-spacing: 0.5px;">&copy; 2024 COUTURIER DIGITAL - L'excellence sur mesure.</p>
        </div>
    </div>
    """
    
    text_content = f"Votre code de vérification COUTURIER DIGITAL est : {otp_code}"

    # On crée l'objet email
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=full_sender, # On passe le formataddr ici
        to=[target_email],
        headers={'From': full_sender} # On FORCE le header From pour les serveurs capricieux
    )
    
    msg.attach_alternative(html_content, "text/html")
    
    # Envoi
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

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # 1. Générer les tokens JWT
            refresh = RefreshToken.for_user(user)
            access = refresh.access_token

            # 2. Déterminer le type de profil
            profile_type = 'client'
            if hasattr(user, 'professional_profile'):
                profile_type = 'professionnel'

            return Response({
                'status': status.HTTP_200_OK,
                'data': {
                    'refresh': str(refresh),
                    'access': str(access),
                    'user_info': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'profile_type': profile_type,
                    }
                }
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
    """Envoie le code OTP avec le design COUTURIER DIGITAL."""
    subject = f"{otp_code} est votre code de récupération"
    from_email = formataddr(("COUTURIER DIGITAL", settings.EMAIL_HOST_USER))
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; border: 1px solid #f0f0f0; border-radius: 12px; overflow: hidden;">
        <div style="background-color: #E91E63; padding: 25px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 22px;">COUTURIER DIGITAL</h1>
        </div>
        <div style="padding: 40px 20px; text-align: center;">
            <h2 style="color: #333;">Récupération de compte</h2>
            <p style="color: #666;">Vous avez demandé la réinitialisation de votre mot de passe. Utilisez le code suivant :</p>
            <div style="margin: 30px 0;">
                <span style="font-size: 36px; font-weight: bold; color: #E91E63; letter-spacing: 5px; border: 2px dashed #E91E63; padding: 10px 20px;">{otp_code}</span>
            </div>
            <p style="color: #999; font-size: 12px;">Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.</p>
        </div>
    </div>
    """
    msg = EmailMultiAlternatives(subject, f"Votre code : {otp_code}", from_email, [target_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send()


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
                user = User.objects.get(email=email)
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
                user = User.objects.get(email=email)
                user.set_password(new_password)
                user.save()
                
                # Supprimer le cache après succès
                cache.delete(f"password_reset_{email}")
                return Response({"message": "Mot de passe modifié avec succès !"}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"message": "Une erreur est survenue."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"message": "Étape invalide."}, status=status.HTTP_400_BAD_REQUEST)