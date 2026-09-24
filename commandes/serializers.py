from rest_framework import serializers
from core.models import (
    Commande, LibelleMesure, MesureClient, ModeleCommande, ModeleDisponible, 
    ProfessionalProfile, ClientProfile, ValeurMesureCommande
)

# ============================================================
# 1. PARTIE LECTURE SEULE (DÉTAILS POUR L'AFFICHAGE)
# ============================================================

class ValeurMesureCommandeSerializer(serializers.ModelSerializer):
    """Affiche les mesures telles qu'elles ont été figées à la commande."""
    class Meta:
        model = ValeurMesureCommande
        fields = ['libelle_nom', 'valeur']

class LibelleMesureSerializer(serializers.ModelSerializer):
    # On crée un champ dynamique pour la valeur
    valeur = serializers.SerializerMethodField()

    class Meta:
        model = MesureClient
        fields = ['Libelle ', 'valeur', 'position_x', 'position_y', 'categorie']

    def get_valeur(self, obj):
        # Ici, on cherche la valeur enregistrée pour ce libellé.
        # 'obj' est l'instance de LibelleMesure.
        # On suppose que tu as un modèle 'ValeurMesure' qui lie Libelle et Client.
        try:
            # Remplace 'ValeurMesure' par le nom exact de ton modèle qui stocke les chiffres
            return obj.valeurs.filter(client_profile=obj.client_profile).first().valeur
        except:
            return 0  # Valeur par défaut si rien n'est saisi
class MesureClientSerializer(serializers.ModelSerializer):
    """
    Sert à extraire la valeur depuis MesureClient 
    et le nom depuis le LibelleMesure associé.
    """
    nom = serializers.CharField(source='libelle.nom', read_only=True)
    position_x = serializers.FloatField(source='libelle.position_x', read_only=True)
    position_y = serializers.FloatField(source='libelle.position_y', read_only=True)
    categorie = serializers.CharField(source='libelle.categorie', read_only=True)

    class Meta:
        model = MesureClient
        fields = ['nom', 'valeur', 'position_x', 'position_y', 'categorie']

class ClientProfileMinimalSerializer(serializers.ModelSerializer):
    """Affiche les informations du client avec ses mesures actuelles."""
    username = serializers.CharField(source='user.username', read_only=True)
    
    # Utilise le related_name='mesures_dynamiques' défini dans ton modèle MesureClient
    mesures_client = MesureClientSerializer(many=True, source='mesures_dynamiques', read_only=True)

    class Meta:
        model = ClientProfile
        fields = ['nom', 'prenom', 'username', 'mesures_client']

class ModeleDisponibleDetailSerializer(serializers.ModelSerializer):
    """Affiche les détails du modèle avec URL d'image complète pour Flutter."""
    image = serializers.SerializerMethodField()

    class Meta:
        model = ModeleDisponible
        fields = ['id', 'nom', 'description', 'price', 'acompte', 'image']
        
    def get_image(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
class ModeleCommandeDetailSerializer(serializers.ModelSerializer):
    # URL absolue du modèle personnalisé (commandes/custom/)
    image_personnalisee = serializers.SerializerMethodField()
    # URL absolue de la photo du tissu (commandes/tissu/)
    image_tissu = serializers.SerializerMethodField()
    mesures_figees = ValeurMesureCommandeSerializer(many=True, read_only=True)
    # Le context (request) est passé au sous-serializer via get_modele_disponible
    modele_disponible = serializers.SerializerMethodField()

    class Meta:
        model = ModeleCommande
        fields = [
            'id',
            'modele_disponible',
            'image_personnalisee',   # modèle custom → commandes/custom/
            'image_tissu',           # photo tissu   → commandes/tissu/
            'mesures_figees',
            'prix_unitaire_snapshot'
        ]

    def get_image_personnalisee(self, obj):
        if obj.image_personnalisee:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image_personnalisee.url)
            return obj.image_personnalisee.url
        return None

    def get_modele_disponible(self, obj):
        """Sérialise le modèle disponible en propageant le context (request)."""
        if obj.modele_disponible:
            return ModeleDisponibleDetailSerializer(
                obj.modele_disponible,
                context=self.context  # ← transmet le request au sous-serializer
            ).data
        return None

    def get_image_tissu(self, obj):
        if obj.image_tissu:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image_tissu.url)
            return obj.image_tissu.url
        return None
    
class CommandeDetailSerializer(serializers.ModelSerializer):
    """Le sérialiseur principal pour afficher les listes de commandes (Client & Pro)."""
    articles = ModeleCommandeDetailSerializer(many=True, read_only=True)
    nom_entreprise = serializers.CharField(source='professional_profile.nom_entreprise', read_only=True)
    client_profile = ClientProfileMinimalSerializer(read_only=True)
    
    class Meta:
        model = Commande
        fields = [
            'id', 'client_profile', 'nom_entreprise', 'professional_profile',
            'date_creation', 'date_livraison', 'statut', 'articles',
            'total_commande', 'montant_paye', 'reste_a_payer', 'statut_paiement',
            'moyen_paiement', 'acompte_demande', 'type_paiement',
        ]

# ============================================================
# 2. PARTIE ÉCRITURE (CRÉATION ET MISE À JOUR)
# ============================================================

class ValeurMesureCommandeInputSerializer(serializers.Serializer):
    """Reçoit les mesures saisies côté Flutter pour un article donné."""
    libelle_nom = serializers.CharField(max_length=100)
    valeur = serializers.DecimalField(max_digits=6, decimal_places=2)


class ModeleCommandeSerializer(serializers.ModelSerializer):
    modele_disponible = serializers.PrimaryKeyRelatedField(
        queryset=ModeleDisponible.objects.all(),
        allow_null=True,
        required=False
    )
    # ✅ NOUVEAU : mesures spécifiques à cet article
    mesures = ValeurMesureCommandeInputSerializer(many=True, required=False)

    class Meta:
        model = ModeleCommande
        fields = ['modele_disponible', 'image_personnalisee', 'mesures']


from django.db import transaction

# Dans ton serializers.py (Partie 4 : COMMANDES)

class CommandeSerializer(serializers.ModelSerializer):
    articles = ModeleCommandeSerializer(many=True)

    class Meta:
        model = Commande
        fields = [
            'id', 'client_profile', 'professional_profile', 'date_creation',
            'date_livraison', 'statut', 'montant_paye', 'reste_a_payer',
            'statut_paiement', 'articles', 'total_commande'
        ]
        read_only_fields = ['client_profile', 'montant_paye', 'reste_a_payer', 'statut_paiement']

    def create(self, validated_data):
        # La view gère la création des articles et des mesures
        # On valide juste les données ici, la view fait le vrai travail
        validated_data.pop('articles', None)
        return Commande.objects.create(**validated_data)
    
class CommandeStatusSerializer(serializers.ModelSerializer):
    """Utilisé pour la mise à jour simplifiée du statut (PATCH)."""
    class Meta:
        model = Commande
        fields = ['statut']


class MoyenPaiementSerializer(serializers.ModelSerializer):
    """
    Utilisé juste après la création d'une commande : le client choisit
    comment il compte régler (Mobile Money ou Espèce) et s'il paie la
    totalité ou seulement l'acompte fixé par le couturier sur le modèle.
    """
    class Meta:
        model = Commande
        fields = ['moyen_paiement', 'type_paiement']

    def validate_moyen_paiement(self, value):
        valeurs_valides = dict(Commande.MOYEN_PAIEMENT_CHOICES).keys()
        if value not in valeurs_valides:
            raise serializers.ValidationError(
                "Moyen de paiement invalide. Choisissez 'MOBILE_MONEY' ou 'ESPECE'."
            )
        return value

    def validate_type_paiement(self, value):
        valeurs_valides = dict(Commande.TYPE_PAIEMENT_CHOICES).keys()
        if value not in valeurs_valides:
            raise serializers.ValidationError(
                "Type de paiement invalide. Choisissez 'TOTAL' ou 'ACOMPTE'."
            )
        return value


class DefinirMontantSerializer(serializers.ModelSerializer):
    """
    Utilisé par le PROFESSIONNEL pour indiquer le montant qu'il facture
    pour une commande sur-mesure (image envoyée par le client, sans
    modèle catalogue donc sans prix connu à la création).
    """
    class Meta:
        model = Commande
        fields = ['total_commande']

    def validate_total_commande(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Le montant doit être supérieur à zéro.")
        return value