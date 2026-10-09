from django.db import models

from core.models import OffreAbonnement, ProfessionalProfile


class PaiementChariow(models.Model):
    """
    Une tentative de paiement d'abonnement via Chariow.
    L'abonnement n'est prolongé QUE lorsque le Pulse « successful.sale » arrive
    (jamais sur le retour de la page de paiement). « applique » évite un double crédit.
    """
    STATUTS = [
        ("EN_ATTENTE", "En attente de paiement"),
        ("PAYE", "Payé (abonnement prolongé)"),
        ("ECHEC", "Échec"),
        ("ABANDON", "Abandonné"),
        ("ANOMALIE", "Payé mais à vérifier"),
    ]

    reference = models.CharField(max_length=40, unique=True, db_index=True)
    professional_profile = models.ForeignKey(ProfessionalProfile, on_delete=models.CASCADE,
                                             related_name="paiements_chariow")
    offre = models.ForeignKey(OffreAbonnement, on_delete=models.PROTECT)
    montant_attendu = models.DecimalField(max_digits=10, decimal_places=2)
    statut = models.CharField(max_length=12, choices=STATUTS, default="EN_ATTENTE", db_index=True)
    transaction_id = models.CharField(max_length=100, blank=True)
    checkout_url = models.URLField(max_length=2048, blank=True)
    sale_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    devise = models.CharField(max_length=10, blank=True)
    applique = models.BooleanField(default=False)
    abonnement_jusquau = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    maj_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "Paiement Chariow"
        verbose_name_plural = "Paiements Chariow"

    def __str__(self):
        return f"{self.reference} · {self.offre.nom} · {self.get_statut_display()}"


class PulseChariow(models.Model):
    """
    Chaque livraison de webhook reçue (dédoublonnée sur x-pulse-delivery-id).
    Un même x-pulse-delivery-id revient à chaque nouvel essai de Chariow : on ne le traite qu'une fois.
    """
    delivery_id = models.CharField(max_length=100, unique=True)
    pulse_id = models.CharField(max_length=100, blank=True)
    evenement = models.CharField(max_length=60, blank=True, db_index=True)
    corps = models.JSONField()
    recu_le = models.DateTimeField(auto_now_add=True)
    traite = models.BooleanField(default=False)
    traite_le = models.DateTimeField(null=True, blank=True)
    erreur = models.TextField(blank=True)

    class Meta:
        ordering = ["-recu_le"]
        verbose_name = "Pulse Chariow reçu"
        verbose_name_plural = "Pulses Chariow reçus"

    def __str__(self):
        return f"{self.evenement} · {self.delivery_id}"
