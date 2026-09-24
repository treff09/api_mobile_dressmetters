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

class ProfessionalProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='professional_profile')
    nom_entreprise = models.CharField(max_length=255)
    nom = models.CharField(max_length=100, blank=True)
    prenom = models.CharField(max_length=100, blank=True)
    numero_telephone = models.CharField(max_length=20, blank=True, unique=True)

    def __str__(self):
        return f"Profil Pro - {self.nom_entreprise}"


class ClientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_profile')
    nom = models.CharField(max_length=100, blank=True)
    prenom = models.CharField(max_length=100, blank=True)
    numero_telephone = models.CharField(max_length=20, blank=True, null=True)
    genre = models.CharField(max_length=20, blank=True, null=True)
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
    nom = models.CharField(max_length=100)
    position_x = models.FloatField(default=0.0, help_text="Position horizontale en % sur le gabarit")
    position_y = models.FloatField(default=0.0, help_text="Position verticale en % sur le gabarit")
    categorie = models.CharField(max_length=50, default="Général", help_text="Ex: Haut, Bas, Accessoire")

    class Meta:
        # MODIFICATION : La contrainte d'unicité doit être ajustée 
        # car client_profile peut être null
        unique_together = ('client_profile', 'nom')

    def __str__(self):
        owner = self.client_profile.nom if self.client_profile else "Système"
        return f"{self.nom} ({owner})"


class MesureClient(models.Model):
    """
    Stocke les mesures 'actuelles' du client.
    """
    client_profile = models.ForeignKey(ClientProfile, on_delete=models.CASCADE, related_name='mesures_dynamiques')
    libelle = models.ForeignKey(LibelleMesure, on_delete=models.CASCADE)
    valeur = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    derniere_mise_a_jour = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('client_profile', 'libelle')

    def __str__(self):
        return f"{self.client_profile.user.username} - {self.libelle.nom}: {self.valeur}"

# ============================================================
# PARTIE 3 : ABONNEMENTS
# ============================================================

class OffreAbonnement(models.Model):
    nom = models.CharField(max_length=50, unique=True)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    duree_jours = models.IntegerField(default=30)
    description = models.TextField(blank=True)

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
    nom = models.CharField(max_length=100, unique=True)
    
    def __str__(self): 
        return self.nom


class ModeleDisponible(models.Model):
    professional_profile = models.ForeignKey('ProfessionalProfile', on_delete=models.CASCADE, related_name='modeles')
    type_vetement = models.ForeignKey(TypeVetement, on_delete=models.PROTECT, related_name='modeles_disponibles')
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # Fonction get_image_filename à définir ou remplacer par un chemin standard
    image = models.ImageField(upload_to='modeles/', blank=True, null=True) 
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Montant de l'acompte demandé au client à la commande, DÉCIDÉ PAR LE
    # COUTURIER lui-même (plus de calcul automatique à 50%).
    acompte = models.DecimalField(max_digits=10, decimal_places=2, default=0)

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
    # Photo du tissu fourni par le client
    image_tissu = models.ImageField(
        upload_to=upload_tissu_client,
        null=True,
        blank=True
    )
    prix_unitaire_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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
    def is_valid(self):
        return timezone.now() < self.created_at + datetime.timedelta(minutes=5)


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

    def save(self, *args, **kwargs):
        if self.send_to_all_now and self.global_message:
            all_users = User.objects.all()
            channel_layer = get_channel_layer()
            
            notifications = [Notification(user=u, title=self.global_title, message=self.global_message) for u in all_users]
            Notification.objects.bulk_create(notifications)

            for user in all_users:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user.id}",
                    {"type": "send_notification", "data": {"title": self.global_title, "message": self.global_message, "type": "GLOBAL"}}
                )
            self.send_to_all_now = False
        super().save(*args, **kwargs)


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