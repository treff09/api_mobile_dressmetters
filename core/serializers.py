from rest_framework import serializers
from .models import (
    ClientProfile, OffreAbonnement, TypeVetement, Abonnement,
    ModeleDisponible, Commande, ModeleCommande,
    LibelleMesure, MesureClient, ValeurMesureCommande,
)
from django.db import transaction

# ============================================================
# PARTIE : MESURES DYNAMIQUES
# ============================================================

class LibelleMesureSerializer(serializers.ModelSerializer):
    class Meta:
        model = LibelleMesure
        fields = ['id', 'nom', 'position_x', 'position_y', 'categorie']
class MesureClientSerializer(serializers.ModelSerializer):
    # Champ pour l'écriture (envoyé par Flutter)
    libelle_id = serializers.IntegerField(write_only=True)
    
    # Champs pour la lecture (renvoyés par Django)
    libelle_details = LibelleMesureSerializer(source='libelle', read_only=True)
    libelle_nom = serializers.ReadOnlyField(source='libelle.nom')

    class Meta:
        model = MesureClient
        fields = [
            'id', 
            'libelle',      # L'ID interne (lecture seule par défaut ici)
            'libelle_id',   # L'ID que l'on va utiliser pour sauvegarder
            'libelle_nom', 
            'libelle_details', 
            'valeur', 
            'derniere_mise_a_jour'
        ]
        read_only_fields = ['id', 'derniere_mise_a_jour', 'libelle']
class ClientProfileMinimalSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    
    # On utilise 'mesures_dynamiques' (le related_name défini dans ton modèle MesureClient)
    # pour récupérer les objets complets {nom, valeur}
    mesures_client = MesureClientSerializer(many=True, source='mesures_dynamiques', read_only=True)

    class Meta:
        model = ClientProfile
        fields = ['nom', 'prenom', 'username', 'mesures_client']
class ValeurMesureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValeurMesureCommande
        fields = ['libelle_nom', 'valeur']

# ============================================================
# PARTIE : CATALOGUE & ABONNEMENTS
# ============================================================

class TypeVetementSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeVetement
        fields = '__all__'

class OffreAbonnementSerializer(serializers.ModelSerializer):
    class Meta:
        model = OffreAbonnement
        fields = ['id', 'nom', 'prix', 'duree_jours', 'description']

class AbonnementSerializer(serializers.ModelSerializer):
    est_actif = serializers.ReadOnlyField()
    jours_restants = serializers.ReadOnlyField()

    class Meta:
        model = Abonnement
        fields = '__all__'

class ModeleDisponibleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModeleDisponible
        fields = ['id', 'professional_profile', 'type_vetement', 'nom', 'description', 'image', 'price', 'acompte']
        read_only_fields = ['professional_profile']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request.user, 'professional_profile'):
            validated_data['professional_profile'] = request.user.professional_profile
        return super().create(validated_data)

# ============================================================
# PARTIE : COMMANDES
# ============================================================

from rest_framework import serializers

class ModeleCommandeSerializer(serializers.ModelSerializer):
    # On autorise explicitement modele_disponible à être nul pour le sur-mesure
    modele_disponible = serializers.PrimaryKeyRelatedField(
        queryset=ModeleDisponible.objects.all(),
        allow_null=True,
        required=False
    )

    class Meta:
        model = ModeleCommande
        fields = ['modele_disponible', 'image_personnalisee', 'prix_unitaire_snapshot']

class CommandeSerializer(serializers.ModelSerializer):
    articles = ModeleCommandeSerializer(many=True)

    class Meta:
        model = Commande
        fields = [
            'id', 'client_profile', 'professional_profile', 'date_creation', 
            'date_livraison', 'statut', 'montant_paye', 'reste_a_payer', 
            'statut_paiement', 'articles'
        ]
        read_only_fields = ['client_profile', 'montant_paye', 'reste_a_payer', 'statut_paiement']

    def create(self, validated_data):
        articles_data = validated_data.pop('articles')
        with transaction.atomic():
            commande = Commande.objects.create(**validated_data)
            for article_data in articles_data:
                # On retire les mesures si elles sont passées, car le SIGNAL gère ça
                article_data.pop('mesures', None)
                # On crée juste l'article
                ModeleCommande.objects.create(commande=commande, **article_data)
        return commande