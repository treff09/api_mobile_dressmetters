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
        extra_kwargs = {"password": {"write_only": True}}

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

    def create(self, validated_data):
        # 1. Créer l'utilisateur
        user_data = validated_data.pop('user')
        user = User.objects.create_user(**user_data)
        
        # 2. Créer le profil pro
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

        try:
            user_obj = User.objects.get(email=email)
            username = user_obj.username
        except User.DoesNotExist:
            raise serializers.ValidationError("Adresse e-mail ou mot de passe incorrect.")

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
        fields = ['user', 'nom_entreprise', 'nom', 'prenom', 'numero_telephone']

class ClientProfileSerializer(serializers.ModelSerializer):
    user = UserSimpleSerializer(read_only=True)
    class Meta:
        model = ClientProfile
        fields = ['user', 'nom', 'prenom', 'numero_telephone']