from celery import shared_task
from django.core.management import call_command


@shared_task(name="accounts.effacer_comptes_supprimes")
def effacer_comptes_supprimes():
    """
    Chaque nuit (Celery Beat) : efface les données personnelles des comptes supprimés
    depuis plus longtemps que le délai réglé dans l'admin (App configuration).
    """
    call_command("effacer_comptes_supprimes")
