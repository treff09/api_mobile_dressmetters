"""Nouveau compte couturier → offre d'ouverture (si la période est en cours)."""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import ProfessionalProfile


@receiver(post_save, sender=ProfessionalProfile)
def offre_a_la_creation(sender, instance, created, **kwargs):
    if created and not kwargs.get('raw'):
        from core.offre_ouverture import offrir_mois_ouverture
        transaction.on_commit(lambda: offrir_mois_ouverture(instance))
