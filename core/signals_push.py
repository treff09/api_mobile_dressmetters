"""Chaque Notification enregistrée part aussi sur le téléphone (si Firebase est configuré)."""
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Notification


@receiver(post_save, sender=Notification)
def notification_vers_telephone(sender, instance, created, **kwargs):
    if not created:
        return
    import os
    if not os.getenv('FIREBASE_CREDENTIALS'):
        return  # Firebase pas encore configuré : rien à envoyer sur le téléphone

    def _envoyer():
        try:
            from core.tasks_suivi import envoyer_push_notification
            envoyer_push_notification.delay(instance.id)
        except Exception:  # Celery arrêté : envoi direct
            from core.push import envoyer_push
            envoyer_push(instance.user, instance.title, instance.message,
                         {"commande_id": instance.commande_id, "notification_id": instance.id})

    transaction.on_commit(_envoyer)
