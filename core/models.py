import datetime
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .utils import get_image_filename
import os
import uuid
User = get_user_model()

# ============================================================
# PARTIE 1 : PROFILS UTILISATEURS
# ============================================================

DEVISES = [
    ('XOF', 'Franc CFA (UEMOA) — FCFA'), ('XAF', 'Franc CFA (CEMAC) — FCFA'),
    ('EUR', 'Euro — €'), ('USD', 'Dollar américain — $'), ('GBP', 'Livre sterling — £'),
    ('CAD', 'Dollar canadien — $ CA'), ('CHF', 'Franc suisse — CHF'),
    ('GHS', 'Cedi ghanéen — GH₵'), ('NGN', 'Naira — ₦'), ('MAD', 'Dirham marocain — DH'),
    ('GNF', 'Franc guinéen — FG'), ('CDF', 'Franc congolais — FC'), ('KES', 'Shilling kényan — KSh'),
    ('ZAR', 'Rand — R'),
]


class ProfessionalProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='professional_profile')
    nom_entreprise = models.CharField(max_length=255)
    nom = models.CharField(max_length=100, blank=True)
    prenom = models.CharField(max_length=100, blank=True)
    numero_telephone = models.CharField(max_length=20, blank=True, unique=True)
    # Localisation de l'atelier (carte « couturiers près de moi »)
    ville = models.CharField(max_length=80, blank=True, default='')
    quartier = models.CharField(max_length=120, blank=True, default='')
    adresse = models.CharField(max_length=255, blank=True, default='', help_text="Repère : « Près de la pharmacie… »")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    visible_sur_carte = models.BooleanField(default=True)
    # Parrainage : « Invite un couturier, gagne 1 mois Premium »
    code_parrainage = models.CharField(max_length=12, unique=True, null=True, blank=True)
    parrain = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='filleuls')
    parrainage_recompense = models.BooleanField(default=False, help_text="Le parrain a déjà reçu son mois offert pour ce filleul")
    # Devise des prix de l'atelier (modèles, commandes, paiements reçus). N'affecte pas l'abonnement.
    devise = models.CharField(max_length=3, choices=DEVISES, default='XOF')
    # Le couturier a choisi sa devise (question posée à la première connexion)
    devise_confirmee = models.BooleanField(default=False)
    # Nombre de modèles retirés du catalogue (limité sans abonnement)
    nb_retraits = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        # Un même compte ne peut pas être client ET couturier
        if not self.pk and ClientProfile.objects.filter(user_id=self.user_id).exists():
            from django.core.exceptions import ValidationError
            raise ValidationError("Ce compte est déjà un compte client : il ne peut pas être aussi couturier.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Profil Pro - {self.nom_entreprise}"


class ClientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_profile')
    nom = models.CharField(max_length=100, blank=True)
    prenom = models.CharField(max_length=100, blank=True)
    numero_telephone = models.CharField(max_length=20, blank=True, null=True)
    genre = models.CharField(max_length=20, blank=True, null=True)
    # Client enregistré par un couturier (il n'a pas encore l'application).
    # Ses commandes et mesures rejoignent son vrai compte quand il ouvre
    # son lien de suivi et s'inscrit (voir commandes/views_sans_appli.py).
    invite = models.BooleanField(default=False)
    def save(self, *args, **kwargs):
        # Un même compte ne peut pas être client ET couturier
        if not self.pk and ProfessionalProfile.objects.filter(user_id=self.user_id).exists():
            from django.core.exceptions import ValidationError
            raise ValidationError("Ce compte est déjà un compte couturier : il ne peut pas être aussi client.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Profil Client - {self.user.username}"


# ============================================================
# PARTIE 2 : SYSTÈME DE MESURES DYNAMIQUES (TA VISION)
# ============================================================
class LibelleMesure(models.Model):
    """
    Défini par le Professionnel OU par le système (si professional_profile est null).
    Permet de placer des points sur un gabarit visuel.
    """
    # MODIFICATION : On autorise null=True et blank=True
    client_profile = models.ForeignKey(
        ClientProfile, 
        on_delete=models.SET_NULL, # SET_NULL évite de supprimer les mesures si le pro part
        related_name='mesures_client',
        null=True,   # Permet les mesures standards (système)
        blank=True   # Permet de ne pas remplir le champ dans l'admin/formulaires
    )
    # Mesure créée par un couturier (visible uniquement par lui et ses clients)
    professional_profile = models.ForeignKey(
        'ProfessionalProfile',
        on_delete=models.CASCADE,
        related_name='mesures_perso',
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=100)
    position_x = models.FloatField(default=0.0, help_text="Position horizontale en % sur le gabarit")
    position_y = models.FloatField(default=0.0, help_text="Position verticale en % sur le gabarit")
    categorie = models.CharField(max_length=50, default="Général", help_text="Ex: Haut, Bas, Accessoire")

    # ── Bibliothèque de mesures (mode guidé) ─────────────────────────
    TYPE_CHOICES = [('TOUR', 'Tour (point)'), ('LONGUEUR', 'Longueur (trait)')]
    cle = models.CharField(max_length=50, blank=True, null=True, db_index=True,
                           help_text="Identifiant stable, ex: tour_cou")
    type_mesure = models.CharField(max_length=10, choices=TYPE_CHOICES, default='TOUR')
    aide = models.CharField(max_length=200, blank=True, default='',
                            help_text="Phrase affichée au client : comment prendre la mesure")
    ordre = models.PositiveIntegerField(default=0)
    # Afficher ce point sur la page « Mes mensurations » même sans valeur
    afficher_par_defaut = models.BooleanField(default=True)
    # Positions calées sur chaque silhouette (% du cadre du gabarit).
    # Pour une LONGUEUR : position = point de départ, fin = point d'arrivée.
    position_x_h = models.FloatField(null=True, blank=True)
    position_y_h = models.FloatField(null=True, blank=True)
    fin_x_h = models.FloatField(null=True, blank=True)
    fin_y_h = models.FloatField(null=True, blank=True)
    position_x_f = models.FloatField(null=True, blank=True)
    position_y_f = models.FloatField(null=True, blank=True)
    fin_x_f = models.FloatField(null=True, blank=True)
    fin_y_f = models.FloatField(null=True, blank=True)
    # Où placer le numéro le long du trait (0 = départ, 1 = arrivée)
    label_t = models.FloatField(default=0.5)

    def positions_pour(self, genre):
        """Retourne (x, y, fin_x, fin_y) pour la silhouette du genre donné."""
        homme = str(genre or '').strip().lower() in ('h', 'homme', 'm', 'masculin')
        if homme and self.position_x_h is not None:
            return self.position_x_h, self.position_y_h, self.fin_x_h, self.fin_y_h
        if not homme and self.position_x_f is not None:
            return self.position_x_f, self.position_y_f, self.fin_x_f, self.fin_y_f
        return self.position_x, self.position_y, None, None

    class Meta:
        # MODIFICATION : La contrainte d'unicité doit être ajustée 
        # car client_profile peut être null
        unique_together = ('client_profile', 'nom')

    def __str__(self):
        owner = self.client_profile.nom if self.client_profile else "Système"
        return f"{self.nom} ({owner})"


class PersonneMesuree(models.Model):
    """
    Une personne dont le client garde les mesures : lui-même (« Moi »),
    ses enfants, son conjoint… Ex : une maman qui commande pour Junior et Malik.
    """
    GENRE_CHOICES = [('H', 'Homme / garçon'), ('F', 'Femme / fille')]
    client_profile = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='personnes')
    prenom = models.CharField(max_length=60)
    genre = models.CharField(max_length=1, choices=GENRE_CHOICES, default='F')
    est_moi = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('client_profile', 'prenom')
        ordering = ['-est_moi', 'prenom']

    @staticmethod
    def moi(client_profile):
        """Retourne (et crée si besoin) la personne « Moi » du client."""
        p = client_profile.personnes.filter(est_moi=True).first()
        if p:
            return p
        g = str(client_profile.genre or '').strip().lower()
        genre = 'H' if g in ('h', 'homme', 'm', 'masculin') else 'F'
        prenom = 'Moi'
        while client_profile.personnes.filter(prenom=prenom).exists():
            prenom += ' '
        return PersonneMesuree.objects.create(client_profile=client_profile, prenom=prenom, genre=genre, est_moi=True)

    def __str__(self):
        return f"{self.prenom} ({self.client_profile})"


class MesureClient(models.Model):
    """
    Stocke les mesures 'actuelles' d'une personne suivie par le client.
    """
    client_profile = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='mesures_dynamiques')
    # Pour qui est cette mesure (Moi, Junior…). Toujours rempli par l'API.
    personne = models.ForeignKey(PersonneMesuree, on_delete=models.CASCADE, related_name='mesures',
                                 null=True, blank=True)
    libelle = models.ForeignKey(LibelleMesure, on_delete=models.CASCADE)
    valeur = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    derniere_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('client_profile', 'personne', 'libelle')

    def __str__(self):
        return f"{self.client_profile.user.username} - {self.libelle.nom}: {self.valeur}"


class PositionGabaritClient(models.Model):
    """
    Stocke la position personnalisée (X, Y) d'un point du gabarit pour un client.
    Permet à chaque client de déplacer les points système sans affecter les autres.
    Si aucune entrée n'existe pour un point, la position par défaut du LibelleMesure est utilisée.
    """
    client_profile = models.ForeignKey(
        ClientProfile,
        on_delete=models.CASCADE,
        related_name='positions_gabarit'
    )
    libelle = models.ForeignKey(
        LibelleMesure,
        on_delete=models.CASCADE,
        related_name='positions_clients'
    )
    position_x = models.FloatField(default=0.0)
    position_y = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('client_profile', 'libelle')
        verbose_name = "Position gabarit client"
        verbose_name_plural = "Positions gabarit clients"

    def __str__(self):
        return f"{self.client_profile.user.username} - {self.libelle.nom}: ({self.position_x}, {self.position_y})"

# ============================================================
# PARTIE 3 : ABONNEMENTS
# ============================================================

class OffreAbonnement(models.Model):
    nom = models.CharField(max_length=50, unique=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    duree_jours = models.IntegerField(default=30)
    description = models.TextField(blank=True)
    # Identifiant (ou slug) du produit correspondant sur Chariow, ex. « prd_abc123 ».
    # Vide = offre non payable en ligne.
    chariow_product_id = models.CharField(max_length=100, blank=True, default='')
    actif = models.BooleanField(default=True, help_text="Décocher pour masquer l'offre dans l'application.")

    def __str__(self):
        return f"{self.nom} ({self.prix} FCFA)"


class Abonnement(models.Model):
    professional_profile = models.OneToOneField(ProfessionalProfile, on_delete=models.CASCADE, related_name='abonnement')
    offre = models.ForeignKey(OffreAbonnement, on_delete=models.PROTECT, null=True)
    date_debut = models.DateField(auto_now_add=True)
    date_fin = models.DateTimeField()

    @property
    def est_actif(self):
        from django.utils import timezone
        return bool(self.date_fin and self.date_fin > timezone.now())

    @property
    def jours_restants(self):
        from django.utils import timezone
        if not self.date_fin:
            return 0
        diff = (self.date_fin - timezone.now()).days
        return max(diff, 0)

    def __str__(self):
        return f"Abonnement de {self.professional_profile.nom_entreprise}"


 
class AbonnementPaiement(models.Model):
    """
    Trace chaque tentative de paiement d'abonnement via la gateway.
    'applied' passe à True une fois l'abonnement effectivement prolongé,
    pour éviter un double crédit si la page de confirmation est rechargée
    ou pollée plusieurs fois.
    """
 
    STATUS_CHOICES = [
        ("PENDING", "En attente"),
        ("SUCCESSFUL", "Réussi"),
        ("FAILED", "Échoué"),
    ]
    PROVIDER_CHOICES = [
        ("mtn_momo", "MTN MoMo"),
        ("orange_money", "Orange Money"),
        ("wave", "Wave"),
    ]
 
    order_id = models.CharField(max_length=64, unique=True, db_index=True)
    professional_profile = models.ForeignKey(
        ProfessionalProfile, on_delete=models.CASCADE, related_name="paiements_abonnement"
    )
    offre = models.ForeignKey(OffreAbonnement, on_delete=models.PROTECT)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PENDING")
    applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    def __str__(self):
        return f"{self.order_id} - {self.status}"

# ============================================================
# PARTIE 4 : MODÈLES & COMMANDES
# ============================================================
class TypeVetement(models.Model):
    nom = models.CharField(max_length=100)
    # null = type proposé par l'application ; sinon type créé par un couturier
    professional_profile = models.ForeignKey(
        'ProfessionalProfile',
        on_delete=models.CASCADE,
        related_name='types_perso',
        null=True,
        blank=True,
    )
    # Mesures demandées par défaut pour ce type de vêtement
    mesures_requises = models.ManyToManyField(
        'LibelleMesure', blank=True, related_name='types_vetement'
    )

    class Meta:
        unique_together = ('professional_profile', 'nom')

    def __str__(self): 
        return self.nom


class ModeleDisponible(models.Model):
    professional_profile = models.ForeignKey('ProfessionalProfile', on_delete=models.CASCADE, related_name='modeles')
    type_vetement = models.ForeignKey(TypeVetement, on_delete=models.PROTECT, related_name='modeles_disponibles')
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # Fonction get_image_filename à définir ou remplacer par un chemin standard
    image = models.ImageField(upload_to='modeles/', blank=True, null=True)  # vue de FACE (principale)
    # Autres vues, facultatives : le client vérifie bien le modèle avant de commander
    image_cote = models.ImageField(upload_to='modeles/', blank=True, null=True)
    image_dos = models.ImageField(upload_to='modeles/', blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Montant de l'acompte demandé au client à la commande, DÉCIDÉ PAR LE
    # COUTURIER lui-même (plus de calcul automatique à 50%).
    acompte = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Retiré du catalogue : invisible pour les clients, mais les commandes
    # déjà passées gardent sa photo et ses informations.
    actif = models.BooleanField(default=True, verbose_name="En ligne dans le catalogue")
    date_retrait = models.DateTimeField(null=True, blank=True)
    # Mesures choisies par le couturier pour CE modèle.
    # Si vide, on utilise celles du type de vêtement.
    mesures_requises = models.ManyToManyField(
        'LibelleMesure', blank=True, related_name='modeles'
    )

    def mesures_a_prendre(self):
        """Mesures à demander au client pour ce modèle (modèle > type)."""
        propres = self.mesures_requises.all()
        if propres.exists():
            return propres.order_by('ordre', 'id')
        return self.type_vetement.mesures_requises.all().order_by('ordre', 'id')

    def __str__(self): 
        return f"{self.nom} - {self.professional_profile.nom_entreprise}"


class Commande(models.Model):
    STATUT_PAIEMENT_CHOICES = [
        ('EN_ATTENTE', 'En attente'),
        ('ACOMPTE_PAYE', 'Acompte payé'),
        ('TOTALEMENT_PAYE', 'Totalement payé'),
    ]

    MOYEN_PAIEMENT_CHOICES = [
        ('MOBILE_MONEY', 'Mobile Money'),
        ('ESPECE', 'Espèce'),
    ]

    TYPE_PAIEMENT_CHOICES = [
        ('TOTAL', 'Paiement total'),
        ('ACOMPTE', 'Acompte'),
    ]
    
    client_profile = models.ForeignKey('ClientProfile', on_delete=models.CASCADE, related_name='commandes')
    professional_profile = models.ForeignKey('ProfessionalProfile', on_delete=models.CASCADE, related_name='commandes_recues')
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_livraison = models.DateTimeField(default=timezone.now, null=True, blank=True)
    
    statut = models.CharField(max_length=50, default='En attente')

    # Étapes de fabrication (le client est prévenu à chaque étape)
    ETAPES = [
        ('RECUE', 'Commande reçue'),
        ('COUPE', 'Coupe du tissu'),
        ('COUTURE', 'Couture'),
        ('ESSAYAGE', 'Prête pour essayage'),
        ('PRETE', 'Prête à récupérer'),
        ('LIVREE', 'Livrée'),
    ]
    etape = models.CharField(max_length=12, choices=ETAPES, default='RECUE')
    etape_maj_le = models.DateTimeField(null=True, blank=True)
    date_essayage = models.DateTimeField(null=True, blank=True)
    
    # Finances
    total_commande = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reste_a_payer = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut_paiement = models.CharField(max_length=20, choices=STATUT_PAIEMENT_CHOICES, default='EN_ATTENTE')
    # Acompte demandé, calculé à partir des acomptes DÉCIDÉS PAR LE COUTURIER
    # sur chacun de ses modèles (et non plus un forfait de 50% imposé par l'app).
    # Purement informatif : aucun montant n'est prélevé automatiquement dans
    # l'application, le règlement se fait hors-app (Mobile Money / Espèce).
    acompte_demande = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Moyen de paiement choisi par le client APRÈS la validation de la commande
    # (Mobile Money ou Espèce). Vide tant que le client n'a pas encore choisi.
    moyen_paiement = models.CharField(
        max_length=20, choices=MOYEN_PAIEMENT_CHOICES, null=True, blank=True
    )

    # Le client choisit, au même moment, s'il compte régler la totalité ou
    # seulement l'acompte (montant fixé par le couturier sur chaque modèle).
    # Purement indicatif : sert à informer le couturier de ce à quoi
    # s'attendre (aucun mouvement d'argent réel dans l'application).
    type_paiement = models.CharField(
        max_length=10, choices=TYPE_PAIEMENT_CHOICES, null=True, blank=True
    )

    # Lien de suivi public (page web envoyée au client par WhatsApp)
    lien_suivi = models.CharField(max_length=32, unique=True, null=True, blank=True)
    # Commande saisie par le couturier pour un client sans l'application
    creee_par_couturier = models.BooleanField(default=False)
    # Description libre du vêtement (commande saisie par le couturier sans modèle du catalogue)
    description = models.CharField(max_length=255, blank=True, default='')

    def jeton_suivi(self):
        """Crée (une seule fois) le jeton secret du lien de suivi."""
        if not self.lien_suivi:
            import secrets
            self.lien_suivi = secrets.token_urlsafe(16)[:22]
            Commande.objects.filter(pk=self.pk).update(lien_suivi=self.lien_suivi)
        return self.lien_suivi

    def save(self, *args, **kwargs):
        # Calcul automatique du reste à payer avant sauvegarde
        self.reste_a_payer = self.total_commande - self.montant_paye
        super().save(*args, **kwargs)

    def __str__(self): 
        return f"Commande #{self.id} - {self.client_profile.user.username}"


import os
import uuid
from django.db import models

def upload_modele_personnalise(instance, filename):
    """Modèle dessiné/imaginé par le client (commande sur-mesure sans catalogue)."""
    ext = filename.split('.')[-1]
    new_filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('commandes/custom/', new_filename)

def upload_tissu_client(instance, filename):
    """Photo du tissu fourni par le client pour sa commande."""
    ext = filename.split('.')[-1]
    new_filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('commandes/tissu/', new_filename)

class ModeleCommande(models.Model):
    commande = models.ForeignKey('Commande', on_delete=models.CASCADE, related_name='articles')
    modele_disponible = models.ForeignKey(
        'ModeleDisponible', 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True
    )
    # Photo du modèle personnalisé envoyé par le client (commande sans catalogue)
    image_personnalisee = models.ImageField(
        upload_to=upload_modele_personnalise,
        null=True, 
        blank=True
    )
    # Autres vues du modèle personnalisé (facultatives)
    image_personnalisee_cote = models.ImageField(upload_to=upload_modele_personnalise, null=True, blank=True)
    image_personnalisee_dos = models.ImageField(upload_to=upload_modele_personnalise, null=True, blank=True)
    # Photo du tissu fourni par le client
    image_tissu = models.ImageField(
        upload_to=upload_tissu_client,
        null=True,
        blank=True
    )
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Pour qui est ce vêtement (copie du prénom pour l'historique)
    personne = models.ForeignKey('PersonneMesuree', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='articles')
    personne_nom = models.CharField(max_length=60, blank=True, default='')
    # Type de vêtement choisi par le client pour son propre modèle (sur-mesure)
    type_vetement = models.ForeignKey('TypeVetement', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='articles_sur_mesure')

    def __str__(self): 
        return f"Article #{self.id} de Commande #{self.commande.id}"
    
class ValeurMesureCommande(models.Model):
    """
    FIGE les mesures dynamiques au moment de la commande.
    Même si le client modifie son profil après, ces données restent intactes.
    """
    article_commande = models.ForeignKey(ModeleCommande, on_delete=models.CASCADE, related_name='mesures_figees')
    libelle_nom = models.CharField(max_length=100) # Copie du nom du point (ex: "Tour de cou")
    valeur = models.DecimalField(max_digits=6, decimal_places=2) # Valeur en cm

    class Meta:
        verbose_name = "Mesure Figée"
        verbose_name_plural = "Mesures Figées"

    def __str__(self): 
        return f"{self.libelle_nom}: {self.valeur} cm"

# ============================================================
# PARTIE 5 : QR CODE & WALLET
# ============================================================

class QRToken(models.Model):
    professional_profile = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE)
    token = models.CharField(max_length=22, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # QR de démonstration (examen Google Play) : n'expire pas et sert plusieurs fois.
    # Créé uniquement par : python manage.py qr_demo
    permanent = models.BooleanField(default=False)
    # Premier scan : le QR reste ensuite utilisable 5 minutes (re-scan possible après une fausse manip)
    premier_scan_le = models.DateTimeField(null=True, blank=True)

    DUREE_AVANT_SCAN = datetime.timedelta(minutes=5)   # QR affiché mais pas encore scanné
    DUREE_APRES_SCAN = datetime.timedelta(minutes=5)   # après le 1er scan

    def is_valid(self):
        if self.permanent:
            return True
        now = timezone.now()
        if self.premier_scan_le:
            return now < self.premier_scan_le + self.DUREE_APRES_SCAN
        return now < self.created_at + self.DUREE_AVANT_SCAN

    def marquer_scan(self):
        """Note le premier scan (les scans suivants ne prolongent pas le délai)."""
        if not self.permanent and self.premier_scan_le is None:
            self.premier_scan_le = timezone.now()
            self.save(update_fields=['premier_scan_le'])


# ============================================================
# PARTIE 6 : SYSTÈME CONFIG & NOTIFICATIONS
# ============================================================

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    commande_id = models.IntegerField(null=True, blank=True)
    class Meta: ordering = ['-created_at']


class AppConfiguration(models.Model):
    is_maintenance_mode = models.BooleanField(default=False)
    maintenance_message = models.TextField(default="L'application est en maintenance.")
    global_title = models.CharField(max_length=150, blank=True)
    global_message = models.TextField(blank=True)
    send_to_all_now = models.BooleanField(default=False, verbose_name="🚀 ENVOYER EN TEMPS RÉEL")
    DESTINATAIRES = [('TOUS', 'Tout le monde'), ('CLIENTS', 'Clients seulement'), ('COUTURIERS', 'Couturiers seulement')]
    destinataires = models.CharField(max_length=12, choices=DESTINATAIRES, default='TOUS',
                                     verbose_name="Envoyer à")
    nb_modeles_gratuits = models.PositiveIntegerField(
        default=5,
        verbose_name="Modèles gratuits par couturier",
        help_text="Nombre de modèles qu'un couturier peut publier SANS abonnement Premium.",
    )

    nb_retraits_gratuits = models.PositiveIntegerField(
        default=3,
        verbose_name="Retraits de modèles gratuits par couturier",
        help_text="Nombre de modèles qu'un couturier SANS abonnement peut retirer de son catalogue "
                  "(au total). Avec l'abonnement Premium, c'est illimité.",
    )

    nb_commandes_mensuelles_gratuites = models.PositiveIntegerField(
        default=10,
        verbose_name="Commandes par mois sans abonnement",
        help_text="Nombre de NOUVELLES commandes qu'un couturier SANS abonnement Premium peut recevoir "
                  "par mois (remis à zéro le 1er du mois). Avec Premium, c'est illimité.",
    )

    @classmethod
    def limite_commandes_mensuelles(cls):
        config = cls.objects.first()
        return config.nb_commandes_mensuelles_gratuites if config else 10

    @classmethod
    def limite_modeles_gratuits(cls):
        config = cls.objects.first()
        return config.nb_modeles_gratuits if config else 5

    delai_recuperation_jours = models.PositiveIntegerField(
        default=30,
        verbose_name="Délai de récupération d'un compte supprimé (jours)",
        help_text="Pendant ce délai, un utilisateur qui a supprimé son compte peut le récupérer. "
                  "Ensuite, ses données personnelles sont effacées automatiquement (tâche Celery). "
                  "Pensez à garder le même chiffre dans la politique de confidentialité.",
    )

    @classmethod
    def delai_recuperation(cls):
        config = cls.objects.first()
        return config.delai_recuperation_jours if config else 30

    @classmethod
    def limite_retraits_gratuits(cls):
        config = cls.objects.first()
        return config.nb_retraits_gratuits if config else 3

    def save(self, *args, **kwargs):
        envoyer = self.send_to_all_now and self.global_message
        titre, message, cible = self.global_title or "Dress'Matter", self.global_message, self.destinataires
        self.send_to_all_now = False
        super().save(*args, **kwargs)
        if envoyer:
            # Liste de l'appli + temps réel + TÉLÉPHONES (appli fermée), en arrière-plan
            from django.db import transaction as _tx

            def _lancer():
                try:
                    from core.tasks_suivi import diffuser_message
                    diffuser_message.delay(titre, message, cible)
                except Exception:  # Celery arrêté : envoi direct
                    from core.tasks_suivi import diffuser_message
                    diffuser_message(titre, message, cible)
            _tx.on_commit(_lancer)


class PrivacyPolicy(models.Model):
    titre = models.CharField(max_length=200, default="Politique de Confidentialité")
    contenu = models.TextField(help_text="Vous pouvez utiliser du HTML simple ici")
    derniere_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Politique de Confidentialité"
        verbose_name_plural = "Politique de Confidentialité"

    def __str__(self):
        return f"{self.titre} - {self.derniere_mise_a_jour.strftime('%d/%m/%Y')}"
    
class ConditionGenerale(models.Model):
    titre = models.CharField(max_length=200, default="Conditions Générales d'Utilisation")
    contenu = models.TextField(help_text="Le contrat entre vous et l'utilisateur")
    derniere_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CGU"
        verbose_name_plural = "CGU"

    def __str__(self):
        return f"CGU - {self.derniere_mise_a_jour.strftime('%d/%m/%Y')}"


# ============================================================
# DÉPART D'UN UTILISATEUR : désactivation ou suppression du compte
# ============================================================

class MotifDepart(models.Model):
    """Motifs proposés quand un utilisateur désactive ou supprime son compte (gérés dans l'admin)."""
    libelle = models.CharField(max_length=150)
    demande_precision = models.BooleanField(
        default=False, help_text="Affiche un champ pour écrire le motif (à cocher pour « Autre »)")
    ordre = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['ordre', 'id']
        verbose_name = "Motif de départ"
        verbose_name_plural = "Motifs de départ"

    def __str__(self):
        return self.libelle


class DepartCompte(models.Model):
    """
    Historique des désactivations / suppressions.
    Dans les deux cas le compte est seulement désactivé (user.is_active = False) :
    - DESACTIVATION : pause, réactivable sans limite de temps ;
    - SUPPRESSION   : récupérable pendant le délai réglé dans l'admin (30 jours par défaut),
                      puis les données personnelles sont effacées par la tâche Celery
                      accounts.tasks.effacer_comptes_supprimes (chaque nuit).
    """
    DESACTIVATION = 'DESACTIVATION'
    SUPPRESSION = 'SUPPRESSION'
    ACTION_CHOICES = [(DESACTIVATION, 'Désactivation (pause)'), (SUPPRESSION, 'Suppression (récupérable un temps)')]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='departs')
    action = models.CharField(max_length=15, choices=ACTION_CHOICES)
    motif = models.ForeignKey(MotifDepart, on_delete=models.SET_NULL, null=True, blank=True)
    precision = models.TextField(blank=True, default='', verbose_name="Motif écrit par l'utilisateur")
    date_demande = models.DateTimeField(auto_now_add=True)
    date_reactivation = models.DateTimeField(null=True, blank=True)
    date_effacement = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_demande']
        verbose_name = "Départ d'un compte"
        verbose_name_plural = "Départs des comptes"

    @property
    def en_cours(self):
        return self.date_reactivation is None and self.date_effacement is None

    @property
    def date_limite(self):
        if self.action == self.SUPPRESSION:
            # Délai réglable dans l'admin (App configuration)
            return self.date_demande + datetime.timedelta(days=AppConfiguration.delai_recuperation())
        return None

    @classmethod
    def en_cours_pour(cls, user):
        return cls.objects.filter(user=user, date_reactivation__isnull=True, date_effacement__isnull=True).first()

    def __str__(self):
        return f"{self.user} - {self.get_action_display()} ({self.date_demande:%d/%m/%Y})"




def modeles_visibles(professional_profile):
    """
    Modèles EN LIGNE d'un couturier tels qu'ils doivent apparaître (à lui comme aux clients) :
    - abonnement actif  -> tous ;
    - pas d'abonnement / abonnement terminé -> seulement les N plus récents (limite réglable dans l'admin).
    Vérifié à CHAQUE requête : dès que la date de fin est passée, les modèles en trop disparaissent,
    sans tâche planifiée ni action manuelle. Rien n'est supprimé : ils reviennent au réabonnement.
    """
    from django.utils import timezone
    qs = ModeleDisponible.objects.filter(professional_profile=professional_profile, actif=True).order_by('-id')
    actif = Abonnement.objects.filter(professional_profile=professional_profile, date_fin__gt=timezone.now()).exists()
    if actif:
        return qs
    return qs[:AppConfiguration.limite_modeles_gratuits()]



def quota_commandes(professional_profile):
    """
    Commandes reçues par le couturier ce mois-ci et limite applicable.
    Renvoie {'premium', 'limite' (None si illimité), 'utilisees', 'restantes' (None si illimité), 'atteinte'}.
    Le mois suit le fuseau de l'application (début du mois à 00:00).
    """
    from django.utils import timezone
    now = timezone.localtime()
    debut_mois = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    utilisees = Commande.objects.filter(professional_profile=professional_profile, date_creation__gte=debut_mois).count()
    premium = Abonnement.objects.filter(professional_profile=professional_profile, date_fin__gt=timezone.now()).exists()
    if premium:
        return {'premium': True, 'limite': None, 'utilisees': utilisees, 'restantes': None, 'atteinte': False}
    limite = AppConfiguration.limite_commandes_mensuelles()
    return {'premium': False, 'limite': limite, 'utilisees': utilisees,
            'restantes': max(limite - utilisees, 0), 'atteinte': utilisees >= limite}



# ============================================================
# SUIVI : PAIEMENTS, AVIS, APPAREILS (notifications push)
# ============================================================

class PaiementCommande(models.Model):
    """Argent reçu par le couturier pour une commande (hors appli : espèces / Mobile Money)."""
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name='paiements')
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    moyen = models.CharField(max_length=20, choices=Commande.MOYEN_PAIEMENT_CHOICES, default='ESPECE')
    note = models.CharField(max_length=200, blank=True, default='')
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']


class AvisCouturier(models.Model):
    """Note laissée par le client après la livraison (une par commande)."""
    commande = models.OneToOneField(Commande, on_delete=models.CASCADE, related_name='avis')
    professional_profile = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE, related_name='avis')
    client_profile = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='avis_donnes')
    note = models.PositiveSmallIntegerField()  # 1 à 5
    commentaire = models.TextField(blank=True, default='')
    date = models.DateTimeField(auto_now_add=True)
    visible = models.BooleanField(default=True, help_text="Décocher pour masquer un avis abusif")

    class Meta:
        ordering = ['-date']


def note_moyenne(pro):
    from django.db.models import Avg, Count
    r = AvisCouturier.objects.filter(professional_profile=pro, visible=True).aggregate(m=Avg('note'), n=Count('id'))
    return (round(r['m'], 1) if r['m'] else None), r['n']


class AppareilPush(models.Model):
    """Téléphone qui reçoit les notifications (jeton Firebase Cloud Messaging)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appareils_push')
    token = models.CharField(max_length=512, unique=True)
    plateforme = models.CharField(max_length=10, default='android')
    maj_le = models.DateTimeField(auto_now=True)



class EnvoiMessage(models.Model):
    """Message envoyé par l'admin à une personne, un groupe ou tout le monde (avec historique)."""
    CIBLES = [
        ('PERSONNES', 'Personnes choisies'),
        ('TOUS', 'Tout le monde'),
        ('CLIENTS', 'Tous les clients'),
        ('COUTURIERS', 'Tous les couturiers'),
        ('COUTURIERS_PREMIUM', 'Couturiers Premium'),
        ('COUTURIERS_GRATUITS', 'Couturiers sans abonnement'),
    ]
    titre = models.CharField(max_length=150)
    message = models.TextField()
    cible = models.CharField("Envoyer à", max_length=24, choices=CIBLES, default='PERSONNES')
    personnes = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='messages_recus',
                                       help_text="Seulement si « Personnes choisies ».")
    ville = models.CharField("Ville ou quartier (facultatif)", max_length=80, blank=True, default='',
                             help_text="Limite un groupe de couturiers à une ville / un quartier, ex. Cocody.")
    cree_le = models.DateTimeField(auto_now_add=True)
    envoye_le = models.DateTimeField(null=True, blank=True)
    resultat = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-cree_le']
        verbose_name = "Message envoyé"
        verbose_name_plural = "Messages envoyés"

    def __str__(self):
        return self.titre

    def envoyer(self):
        """Envoie (une seule fois) : liste de l'appli + temps réel + téléphones."""
        if self.envoye_le:
            return
        from django.db import transaction as _tx
        ids = list(self.personnes.values_list('id', flat=True)) if self.cible == 'PERSONNES' else None
        EnvoiMessage.objects.filter(pk=self.pk).update(envoye_le=timezone.now(), resultat="Envoi en cours…")
        pk, titre, message, cible, ville = self.pk, self.titre, self.message, self.cible, self.ville

        def _lancer():
            from core.tasks_suivi import diffuser_message
            try:
                res = diffuser_message.delay(titre, message, cible, ids, ville)
                EnvoiMessage.objects.filter(pk=pk).update(resultat="Envoyé (en arrière-plan)")
            except Exception:  # Celery arrêté : envoi direct
                res = diffuser_message(titre, message, cible, ids, ville)
                EnvoiMessage.objects.filter(pk=pk).update(resultat=str(res)[:200])
        _tx.on_commit(_lancer)


# ── MODÉRATION (exigence Apple 1.2 : signaler et bloquer) ─────────────────────

class Signalement(models.Model):
    """Contenu signalé par un utilisateur. À traiter sous 24 h dans l'admin."""
    TYPES = [('avis', 'Avis'), ('modele', 'Modèle (photo)'), ('utilisateur', 'Utilisateur')]
    MOTIFS = [('inapproprie', 'Contenu choquant ou inapproprié'), ('insulte', 'Insulte ou harcèlement'),
              ('arnaque', 'Arnaque ou fausse information'), ('autre', 'Autre')]
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='signalements_faits')
    type = models.CharField(max_length=20, choices=TYPES)
    objet_id = models.PositiveIntegerField(help_text="ID de l'avis, du modèle ou de l'utilisateur")
    motif = models.CharField(max_length=20, choices=MOTIFS, default='autre')
    details = models.TextField(blank=True, default='')
    date = models.DateTimeField(auto_now_add=True)
    traite = models.BooleanField(default=False, help_text="Coché une fois le signalement examiné")

    class Meta:
        ordering = ['traite', '-date']

    def __str__(self):
        return f"{self.get_type_display()} #{self.objet_id} — {self.get_motif_display()}"


class Blocage(models.Model):
    """« Bloquer » : les deux personnes ne se voient plus (avis, carte, catalogue)."""
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocages_faits')
    bloque = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocages_subis')
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('auteur', 'bloque')


def ids_bloques(user):
    """IDs des utilisateurs bloqués par `user` ou qui ont bloqué `user`."""
    if not getattr(user, 'is_authenticated', False):
        return set()
    a = Blocage.objects.filter(auteur=user).values_list('bloque_id', flat=True)
    b = Blocage.objects.filter(bloque=user).values_list('auteur_id', flat=True)
    return set(a) | set(b)
