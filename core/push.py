"""
Notifications sur le téléphone, même appli fermée (Firebase Cloud Messaging).

Configuration (.env du serveur) :
    FIREBASE_CREDENTIALS=/chemin/vers/compte-de-service.json
(Console Firebase > Paramètres du projet > Comptes de service > Générer une nouvelle clé privée)

Sans ce fichier, rien ne casse : les notifications restent dans l'appli (WebSocket + liste).
"""
import logging
import os

logger = logging.getLogger(__name__)
_app = None
_desactive = False


def _firebase():
    global _app, _desactive
    if _app or _desactive:
        return _app
    chemin = os.getenv('FIREBASE_CREDENTIALS', '').strip()
    if not chemin or not os.path.exists(chemin):
        _desactive = True
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials
        _app = firebase_admin.initialize_app(credentials.Certificate(chemin))
    except Exception as e:  # noqa: BLE001
        logger.error("Firebase indisponible : %s", e)
        _desactive = True
    return _app


def envoyer_push(user, titre, message, donnees=None):
    """Envoie à tous les téléphones de l'utilisateur. Supprime les jetons morts."""
    app = _firebase()
    if app is None:
        return 0
    from firebase_admin import messaging
    from core.models import AppareilPush
    tokens = list(AppareilPush.objects.filter(user=user).values_list('token', flat=True))
    if not tokens:
        return 0
    donnees = {k: str(v) for k, v in (donnees or {}).items() if v is not None}
    msg = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=titre, body=message),
        data=donnees,
        android=messaging.AndroidConfig(priority='high', notification=messaging.AndroidNotification(
            channel_id='dressmatter', sound='default')),
        apns=messaging.APNSConfig(payload=messaging.APNSPayload(aps=messaging.Aps(sound='default'))),
    )
    try:
        rep = messaging.send_each_for_multicast(msg, app=app)
    except Exception as e:  # noqa: BLE001
        logger.error("Envoi push échoué : %s", e)
        return 0
    morts = [tokens[i] for i, r in enumerate(rep.responses)
             if not r.success and r.exception and getattr(r.exception, 'code', '') in (
                 'registration-token-not-registered', 'invalid-argument', 'NOT_FOUND', 'UNREGISTERED')]
    if morts:
        AppareilPush.objects.filter(token__in=morts).delete()
    return rep.success_count


def notifier(user, titre, message, commande_id=None, type_notif='INFO'):
    """Notification complète : liste dans l'appli + temps réel (WebSocket) + téléphone (push)."""
    from core.models import Notification
    Notification.objects.create(user=user, title=titre, message=message, commande_id=commande_id)
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(f"user_{user.id}", {"type": "send_notification", "data": {
                "type": type_notif, "title": titre, "message": message, "commande_id": commande_id}})
    except Exception:  # noqa: BLE001
        pass


def envoyer_push_masse(user_ids, titre, message, donnees=None):
    """Envoie un même message à beaucoup d'utilisateurs, par paquets de 500 téléphones."""
    app = _firebase()
    if app is None:
        return 0
    from firebase_admin import messaging
    from core.models import AppareilPush
    tokens = list(AppareilPush.objects.filter(user_id__in=user_ids).values_list('token', flat=True))
    donnees = {k: str(v) for k, v in (donnees or {}).items() if v is not None}
    envoyes, morts = 0, []
    for i in range(0, len(tokens), 500):
        lot = tokens[i:i + 500]
        msg = messaging.MulticastMessage(
            tokens=lot, notification=messaging.Notification(title=titre, body=message), data=donnees,
            android=messaging.AndroidConfig(priority='high', notification=messaging.AndroidNotification(
                channel_id='dressmatter', sound='default')),
            apns=messaging.APNSConfig(payload=messaging.APNSPayload(aps=messaging.Aps(sound='default'))),
        )
        try:
            rep = messaging.send_each_for_multicast(msg, app=app)
        except Exception as e:  # noqa: BLE001
            logger.error("Envoi push en masse échoué : %s", e)
            continue
        envoyes += rep.success_count
        morts += [lot[k] for k, r in enumerate(rep.responses)
                  if not r.success and r.exception and getattr(r.exception, 'code', '') in (
                      'registration-token-not-registered', 'invalid-argument', 'NOT_FOUND', 'UNREGISTERED')]
    if morts:
        AppareilPush.objects.filter(token__in=morts).delete()
    return envoyes
