"""Traitement en arrière-plan des Pulses Chariow (webhooks)."""
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.models import Abonnement

from .models import PaiementChariow, PulseChariow

log = logging.getLogger(__name__)


def _valeur(montant):
    """Les montants Chariow sont des objets {value, formatted, short, currency}."""
    if isinstance(montant, dict):
        return montant.get("value"), montant.get("currency") or ""
    return montant, ""


def prolonger_abonnement(paiement):
    """Prolonge l'abonnement du pro à partir de max(maintenant, fin actuelle). À appeler dans une transaction."""
    now = timezone.now()
    abo, cree = Abonnement.objects.select_for_update().get_or_create(
        professional_profile=paiement.professional_profile,
        defaults={"offre": paiement.offre, "date_fin": now},
    )
    depart = abo.date_fin if (abo.date_fin and abo.date_fin > now) else now
    abo.date_fin = depart + timedelta(days=paiement.offre.duree_jours)
    abo.offre = paiement.offre
    abo.save()
    return abo.date_fin


def traiter_vente_reussie(corps):
    sale = corps.get("sale") or {}
    meta = sale.get("custom_metadata") or {}
    sale_id = sale.get("id")
    ref = meta.get("paiement_ref")
    if not ref:
        raise ValueError("custom_metadata.paiement_ref absent : vente non liée à l'application.")

    with transaction.atomic():
        p = PaiementChariow.objects.select_for_update().select_related("offre", "professional_profile__user").get(reference=ref)
        if p.applique:
            return f"déjà appliqué ({p.reference})"
        # Contrôles de cohérence : utilisateur et formule doivent correspondre à ce que le serveur a créé
        anomalie = None
        if str(meta.get("user_id")) != str(p.professional_profile.user_id) or str(meta.get("plan")) != str(p.offre_id):
            p.statut = "ANOMALIE"; p.note = f"Métadonnées incohérentes : {meta}"; p.sale_id = sale_id; p.save()
            anomalie = p.note
        if anomalie is None:
            anomalie = _verifier_et_appliquer(p, sale, sale_id)
    if anomalie:
        raise ValueError(anomalie)  # enregistré en ANOMALIE (hors transaction annulée), visible dans l'admin
    _notifier(p)
    return f"abonnement prolongé jusqu'au {p.abonnement_jusquau:%d/%m/%Y} ({p.reference})"


def _verifier_et_appliquer(p, sale, sale_id):
    """Vérifie le montant puis prolonge l'abonnement. Renvoie un message d'anomalie, ou None si appliqué."""
    valeur, devise = _valeur(sale.get("amount"))
    try:
        paye = Decimal(str(valeur)) if valeur is not None else None
    except InvalidOperation:
        paye = None
    p.sale_id = sale_id
    p.montant_paye = paye
    p.devise = devise
    if paye is not None and paye < p.montant_attendu:
        # Payé moins que le prix (ex. code promo non prévu) : on n'active pas, l'admin tranche
        p.statut = "ANOMALIE"
        p.note = f"Montant payé {paye} {devise} < attendu {p.montant_attendu}"
        p.save()
        return p.note
    p.abonnement_jusquau = prolonger_abonnement(p)
    p.statut = "PAYE"
    p.applique = True
    p.save()
    # Parrainage : bonus pour le parrain APRÈS validation du paiement (n'y touche jamais)
    _bonus_parrain_apres_commit(p.professional_profile_id)
    return None


def _bonus_parrain_apres_commit(pro_id):
    from django.db import transaction as _tx

    def _go():
        try:
            from core.models import ProfessionalProfile
            from commandes.views_suivi import recompenser_parrain
            recompenser_parrain(ProfessionalProfile.objects.get(id=pro_id))
        except Exception as e:  # noqa: BLE001
            log.error("Bonus parrainage non appliqué : %s", e)
    _tx.on_commit(_go)


def traiter_vente_ratee(corps, statut):
    sale = corps.get("sale") or {}
    ref = (sale.get("custom_metadata") or {}).get("paiement_ref")
    if not ref:
        return "vente sans référence, ignorée"
    PaiementChariow.objects.filter(reference=ref, applique=False).update(statut=statut, maj_le=timezone.now())
    return f"{ref} -> {statut}"


def _notifier(paiement):
    """Notification en base + temps réel (WebSocket). Ne bloque jamais le traitement."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from core.models import Notification
        user = paiement.professional_profile.user
        msg = f"Ton abonnement {paiement.offre.nom} est actif jusqu'au {paiement.abonnement_jusquau:%d/%m/%Y}."
        Notification.objects.create(user=user, title="Abonnement activé", message=msg)
        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(f"user_{user.id}", {
                "type": "send_notification",
                "data": {"type": "SUBSCRIPTION", "title": "Abonnement activé", "message": msg},
            })
    except Exception as e:  # noqa: BLE001
        log.warning("Notification abonnement non envoyée : %s", e)


@shared_task(bind=True, max_retries=5, default_retry_delay=60, name="rechargements.traiter_pulse")
def traiter_pulse(self, pulse_pk):
    pulse = PulseChariow.objects.get(pk=pulse_pk)
    if pulse.traite:
        return "déjà traité"
    evt = pulse.evenement or (pulse.corps or {}).get("event", "")
    try:
        if evt == "successful.sale":
            res = traiter_vente_reussie(pulse.corps)
        elif evt == "failed.sale":
            res = traiter_vente_ratee(pulse.corps, "ECHEC")
        elif evt == "abandoned.sale":
            res = traiter_vente_ratee(pulse.corps, "ABANDON")
        else:
            res = f"événement {evt} ignoré"
    except PaiementChariow.DoesNotExist:
        pulse.erreur = "Paiement introuvable pour cette référence."
        pulse.save(update_fields=["erreur"])
        log.warning("Pulse %s : paiement introuvable", pulse.delivery_id)
        return pulse.erreur
    except ValueError as e:
        pulse.erreur = str(e); pulse.traite = True; pulse.traite_le = timezone.now()
        pulse.save(update_fields=["erreur", "traite", "traite_le"])
        log.warning("Pulse %s : %s", pulse.delivery_id, e)
        return str(e)
    except Exception as e:  # erreur temporaire (base indisponible…) : on réessaie
        pulse.erreur = repr(e); pulse.save(update_fields=["erreur"])
        raise self.retry(exc=e)
    pulse.traite = True; pulse.traite_le = timezone.now(); pulse.erreur = ""
    pulse.save(update_fields=["traite", "traite_le", "erreur"])
    log.info("Pulse %s : %s", pulse.delivery_id, res)
    return res


@shared_task(name="rechargements.relancer_pulses_en_attente")
def relancer_pulses_en_attente():
    """Filet de sécurité (Celery beat) : retraite les Pulses reçus mais pas encore traités."""
    limite = timezone.now() - timedelta(days=3)
    recents = timezone.now() - timedelta(minutes=2)
    n = 0
    for pk in PulseChariow.objects.filter(traite=False, recu_le__gte=limite, recu_le__lte=recents).values_list("pk", flat=True):
        traiter_pulse.delay(pk); n += 1
    return n


@shared_task(name="rechargements.rappels_fin_abonnement")
def rappels_fin_abonnement():
    """
    Une fois par jour : prévient le couturier 3 jours avant la fin, puis le jour où l'abonnement prend fin.
    Pas de prélèvement automatique : le renouvellement = un nouveau paiement sur le site.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from core.models import Notification

    now = timezone.now()
    cas = [
        (now + timedelta(days=3), now + timedelta(days=4),
         "Ton abonnement Premium se termine dans 3 jours. Renouvelle-le sur notre site pour garder tous tes modèles en ligne."),
        (now - timedelta(days=1), now,
         "Ton abonnement Premium est terminé : seuls tes modèles les plus récents restent visibles. Renouvelle-le sur notre site."),
    ]
    n = 0
    layer = get_channel_layer()
    for debut, fin, msg in cas:
        for abo in Abonnement.objects.filter(date_fin__gte=debut, date_fin__lt=fin).select_related("professional_profile__user"):
            user = abo.professional_profile.user
            Notification.objects.create(user=user, title="Abonnement Premium", message=msg)
            try:
                if layer:
                    async_to_sync(layer.group_send)(f"user_{user.id}", {"type": "send_notification",
                        "data": {"type": "SUBSCRIPTION", "title": "Abonnement Premium", "message": msg}})
            except Exception:  # noqa: BLE001
                pass
            n += 1
    return n
