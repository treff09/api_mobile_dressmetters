"""Tâches Celery : push, rappels d'échéance (client ET couturier), relances de paiement."""
from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task(name='core.envoyer_push_notification')
def envoyer_push_notification(notification_id):
    from core.models import Notification
    from core.push import envoyer_push
    n = Notification.objects.filter(id=notification_id).select_related('user').first()
    if n:
        return envoyer_push(n.user, n.title, n.message,
                            {"commande_id": n.commande_id, "notification_id": n.id})


def _deja(user, titre, commande_id, depuis):
    from core.models import Notification
    return Notification.objects.filter(user=user, title=titre, commande_id=commande_id, created_at__gte=depuis).exists()


@shared_task(name='core.rappels_echeances')
def rappels_echeances():
    """
    Chaque matin :
      • couturier : livraisons dans 3 jours, demain, et en retard ;
      • client    : livraison dans 2 jours / demain, et rappel du reste à payer ;
      • les deux  : essayage prévu demain.
    Une seule notification de chaque sorte par jour et par commande.
    """
    from core.models import Commande
    from core.push import notifier
    now = timezone.localtime()
    aujourdhui = now.replace(hour=0, minute=0, second=0, microsecond=0)
    n = 0
    en_cours = (Commande.objects.exclude(statut__icontains='termin').exclude(etape='LIVREE')
                .select_related('client_profile__user', 'professional_profile__user'))
    for c in en_cours:
        pro_u, cli_u = c.professional_profile.user, c.client_profile.user
        client = f"{c.client_profile.prenom} {c.client_profile.nom}".strip() or "ton client"
        if c.date_livraison:
            jours = (timezone.localtime(c.date_livraison).date() - now.date()).days
            if jours in (3, 1) and not _deja(pro_u, "Livraison proche", c.id, aujourdhui):
                notifier(pro_u, "Livraison proche",
                         f"Commande #{c.id} de {client} à livrer {'demain' if jours == 1 else 'dans 3 jours'}.", c.id)
                n += 1
            if jours < 0 and not _deja(pro_u, "Livraison en retard", c.id, aujourdhui):
                notifier(pro_u, "Livraison en retard",
                         f"Commande #{c.id} de {client} : la date de livraison est dépassée de {-jours} jour(s).", c.id)
                n += 1
            if jours in (2, 1) and not _deja(cli_u, "Ta commande arrive", c.id, aujourdhui):
                msg = f"Ta commande #{c.id} chez {c.professional_profile.nom_entreprise} est prévue {'demain' if jours == 1 else 'dans 2 jours'}."
                if c.reste_a_payer and c.reste_a_payer > 0:
                    msg += f" Reste à payer : {int(c.reste_a_payer):,} F.".replace(',', ' ')
                notifier(cli_u, "Ta commande arrive", msg, c.id)
                n += 1
        if c.date_essayage:
            j = (timezone.localtime(c.date_essayage).date() - now.date()).days
            if j == 1:
                heure = timezone.localtime(c.date_essayage).strftime('%Hh%M')
                for u, t in ((cli_u, f"Essayage demain à {heure} chez {c.professional_profile.nom_entreprise}."),
                             (pro_u, f"Essayage demain à {heure} avec {client} (commande #{c.id}).")):
                    if not _deja(u, "Essayage demain", c.id, aujourdhui):
                        notifier(u, "Essayage demain", t, c.id)
                        n += 1
    return f"{n} rappel(s) envoyé(s)"


@shared_task(name='core.diffuser_message')
def diffuser_message(titre, message, cible='TOUS'):
    """Message de l'admin : liste de l'appli + temps réel + téléphones (appli fermée)."""
    from django.contrib.auth import get_user_model
    from core.models import Notification
    from core.push import envoyer_push_masse
    users = get_user_model().objects.filter(is_active=True)
    if cible == 'CLIENTS':
        users = users.filter(client_profile__isnull=False)
    elif cible == 'COUTURIERS':
        users = users.filter(professional_profile__isnull=False)
    ids = list(users.values_list('id', flat=True))
    Notification.objects.bulk_create([Notification(user_id=i, title=titre, message=message) for i in ids])
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer:
            for i in ids:
                async_to_sync(layer.group_send)(f"user_{i}", {"type": "send_notification",
                                                             "data": {"title": titre, "message": message, "type": "GLOBAL"}})
    except Exception:  # noqa: BLE001  (temps réel indisponible : la liste et les téléphones suffisent)
        pass
    envoyes = envoyer_push_masse(ids, titre, message, {"type": "GLOBAL"})
    return f"{len(ids)} destinataire(s), {envoyes} téléphone(s) notifié(s)"
