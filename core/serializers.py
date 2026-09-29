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

def genre_du_contexte(context):
    """Genre de la silhouette à utiliser : contexte explicite, sinon celui du client."""
    if context.get('genre'):
        return context['genre']
    request = context.get('request')
    user = getattr(request, 'user', None)
    profil = getattr(user, 'client_profile', None) if user and user.is_authenticated else None
    return getattr(profil, 'genre', None) or 'F'


class LibelleMesureSerializer(serializers.ModelSerializer):
    """
    position_x / position_y sont renvoyés POUR LA SILHOUETTE DU CLIENT
    (homme ou femme). fin_x / fin_y ne sont remplis que pour une LONGUEUR.
    """
    fin_x = serializers.SerializerMethodField()
    fin_y = serializers.SerializerMethodField()
    personnalise = serializers.SerializerMethodField()

    class Meta:
        model = LibelleMesure
        fields = ['id', 'nom', 'cle', 'type_mesure', 'aide', 'ordre', 'label_t',
                  'position_x', 'position_y', 'fin_x', 'fin_y', 'categorie',
                  'afficher_par_defaut', 'personnalise']
        read_only_fields = ['cle', 'ordre', 'afficher_par_defaut']

    def _pos(self, obj):
        return obj.positions_pour(genre_du_contexte(self.context))

    def get_fin_x(self, obj): return self._pos(obj)[2]
    def get_fin_y(self, obj): return self._pos(obj)[3]
    def get_personnalise(self, obj):
        return obj.client_profile_id is not None or obj.professional_profile_id is not None

    def to_representation(self, obj):
        data = super().to_representation(obj)
        x, y, _, _ = self._pos(obj)
        data['position_x'], data['position_y'] = x, y
        return data
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
    mesures_requises = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=LibelleMesure.objects.all()
    )
    personnalise = serializers.SerializerMethodField()

    class Meta:
        model = TypeVetement
        fields = ['id', 'nom', 'mesures_requises', 'personnalise']

    def get_personnalise(self, obj):
        return obj.professional_profile_id is not None

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
    # Lecture : ids des mesures choisies pour ce modèle
    mesures_requises = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    # Écriture : "12,15,18" (plus simple à envoyer en multipart depuis Flutter)
    mesures_requises_ids = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = ModeleDisponible
        fields = ['id', 'professional_profile', 'type_vetement', 'nom', 'description', 'image', 'price', 'acompte',
                  'mesures_requises', 'mesures_requises_ids']
        read_only_fields = ['professional_profile']

    def _appliquer_mesures(self, modele, brut):
        if brut is None:
            return
        ids = [int(x) for x in str(brut).replace(' ', '').split(',') if x.isdigit()]
        modele.mesures_requises.set(LibelleMesure.objects.filter(id__in=ids))

    def create(self, validated_data):
        brut = validated_data.pop('mesures_requises_ids', None)
        request = self.context.get('request')
        if request and hasattr(request.user, 'professional_profile'):
            validated_data['professional_profile'] = request.user.professional_profile
        modele = super().create(validated_data)
        self._appliquer_mesures(modele, brut)
        return modele

    def update(self, instance, validated_data):
        brut = validated_data.pop('mesures_requises_ids', None)
        modele = super().update(instance, validated_data)
        self._appliquer_mesures(modele, brut)
        return modele

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