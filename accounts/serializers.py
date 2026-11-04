from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from core.models import ClientProfile, ProfessionalProfile, LibelleMesure, MesureClient

# ============================================================
# PARTIE 1 : AUTHENTIFICATION & PROFIL DE BASE
# ============================================================

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "email", "password"]
        extra_kwargs = {"password": {"write_only": True}, "email": {"required": True, "allow_blank": False}}

    def validate_email(self, value):
        """
        UN SEUL compte par adresse e-mail (sans tenir compte des majuscules).
        Un compte en pause ou supprimé mais encore récupérable garde son e-mail ;
        seul un compte effacé définitivement libère l'adresse.
        """
        email = (value or '').strip().lower()
        existant = User.objects.filter(email__iexact=email).first()
        if existant:
            if not existant.is_active:
                raise serializers.ValidationError(
                    "Un compte existe déjà avec cet e-mail. Il est en pause ou supprimé : "
                    "connecte-toi avec cet e-mail pour le récupérer.")
            raise serializers.ValidationError(
                "Un compte existe déjà avec cet e-mail. Connecte-toi, ou utilise « Mot de passe oublié ».")
        return email

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

class UserSimpleSerializer(serializers.ModelSerializer):
    """Version légère pour l'affichage dans les profils"""
    class Meta:
        model = User
        fields = ['username', 'email']

# ============================================================
# PARTIE 2 : INSCRIPTION (AVEC INITIALISATION 0.0)
# ============================================================

class ClientRegistrationSerializer(serializers.Serializer):
    user = UserSerializer()
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    numero_telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    genre = serializers.ChoiceField(choices=[('H', 'Homme'), ('F', 'Femme')], required=False)
    def create(self, validated_data):
        # 1. Créer l'utilisateur
        user_data = validated_data.pop("user")
        user = User.objects.create_user(**user_data)

        # 2. Créer le profil client
        client_profile = ClientProfile.objects.create(user=user, **validated_data)

        return client_profile

class ProfessionalRegistrationSerializer(serializers.Serializer):
    user = UserSerializer()
    nom_entreprise = serializers.CharField(max_length=255)
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    numero_telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    # Code d'un couturier qui l'a invité (facultatif)
    code_parrainage = serializers.CharField(max_length=12, required=False, allow_blank=True, write_only=True)

    def validate_code_parrainage(self, v):
        v = (v or '').strip().upper()
        if v and not ProfessionalProfile.objects.filter(code_parrainage=v).exists():
            raise serializers.ValidationError("Code de parrainage inconnu.")
        return v

    def create(self, validated_data):
        code = validated_data.pop('code_parrainage', '')
        # 1. Créer l'utilisateur
        user_data = validated_data.pop('user')
        user = User.objects.create_user(**user_data)
        
        # 2. Créer le profil pro
        if code:
            validated_data['parrain'] = ProfessionalProfile.objects.filter(code_parrainage=code).first()
        pro_profile = ProfessionalProfile.objects.create(user=user, **validated_data)

        return pro_profile

# ============================================================
# PARTIE 3 : LOGIN & MOT DE PASSE
# ============================================================

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        user_obj = User.objects.filter(email__iexact=(email or '').strip()).first()
        if not user_obj:
            raise serializers.ValidationError("Adresse e-mail ou mot de passe incorrect.")
        username = user_obj.username

        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError("Identifiants incorrects.")
        
        data['user'] = user
        return data

class ChangePasswordSerializer(serializers.Serializer):
    ancien_mot_de_passe = serializers.CharField(required=True)
    nouveau_mot_de_passe = serializers.CharField(required=True)
    confirmation_mot_de_passe = serializers.CharField(required=True)

    def validate(self, data):
        if data['nouveau_mot_de_passe'] != data['confirmation_mot_de_passe']:
            raise serializers.ValidationError("Les mots de passe ne correspondent pas.")
        validate_password(data['nouveau_mot_de_passe'])
        return data

# ============================================================
# PARTIE 4 : AFFICHAGE DES PROFILS
# ============================================================

class ProfessionalProfileSerializer(serializers.ModelSerializer):
    user = UserSimpleSerializer(read_only=True)
    class Meta:
        model = ProfessionalProfile
        fields = ['user', 'nom_entreprise', 'nom', 'prenom', 'numero_telephone',
                  'ville', 'quartier', 'adresse', 'latitude', 'longitude', 'visible_sur_carte']

class ClientProfileSerializer(serializers.ModelSerializer):
    user = UserSimpleSerializer(read_only=True)
    class Meta:
        model = ClientProfile
        fields = ['user', 'nom', 'prenom', 'numero_telephone']