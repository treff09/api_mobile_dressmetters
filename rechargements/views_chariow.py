"""
Abonnements payés via Chariow — le paiement se fait sur le SITE WEB (jamais dans l'application).

Site  : /accounts/web-login/ -> /payments/recharge/ -> /payments/payer/<offre>/ (POST)
        -> page Chariow -> retour sur /payments/attente/<ref>/ (attend la confirmation)
Chariow -> POST /api/v1/subscription/chariow/pulse/   webhook signé : SEUL déclencheur de l'activation
"""
import json
import logging
import secrets

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


from . import chariow
from .models import PaiementChariow, PulseChariow
from .tasks import traiter_pulse

log = logging.getLogger(__name__)


def _lancer(pk):
    """Envoie le traitement à Celery. Si Celery est indisponible, la tâche planifiée le rattrapera."""
    try:
        traiter_pulse.delay(pk)
    except Exception as e:  # noqa: BLE001
        log.error("Celery indisponible, Pulse %s traité plus tard : %s", pk, e)


def _nouvelle_reference():
    return "DM-" + timezone.now().strftime("%y%m%d") + "-" + secrets.token_hex(5).upper()


class PaiementImpossible(Exception):
    """Message à afficher tel quel à l'utilisateur."""


def demarrer_paiement_chariow(request, pro, offre, telephone_brut, redirect_url=None):
    """
    Crée le paiement côté serveur puis le checkout Chariow. Renvoie le PaiementChariow
    (avec checkout_url). « {ref} » dans redirect_url est remplacé par la référence du paiement.
    N'active RIEN : seul le Pulse « successful.sale » active l'abonnement.
    Utilisé par le site web (commandes.views.web_payer_abonnement_view).
    """
    user = pro.user
    if not offre.chariow_product_id:
        raise PaiementImpossible("Cette formule n'est pas encore payable en ligne.")
    tel = chariow.telephone_chariow(telephone_brut)
    if tel is None:
        raise PaiementImpossible("Numéro de téléphone invalide.")
    if not user.email:
        raise PaiementImpossible("Ajoute une adresse e-mail à ton compte pour payer.")

    paiement = PaiementChariow.objects.create(
        reference=_nouvelle_reference(), professional_profile=pro, offre=offre, montant_attendu=offre.prix)
    try:
        data = chariow.creer_checkout(
            product_id=offre.chariow_product_id,
            email=user.email,
            prenom=pro.prenom or user.first_name,
            nom=pro.nom or user.last_name,
            telephone=tel,
            customer_ip=chariow.ip_client(request),
            metadata={"user_id": user.id, "plan": offre.id, "paiement_ref": paiement.reference},
            redirect_url=redirect_url.replace("{ref}", paiement.reference) if redirect_url else None,
        )
    except chariow.ChariowError as e:
        paiement.statut = "ECHEC"; paiement.note = f"{e} {e.errors}"; paiement.save()
        log.error("Chariow checkout refusé (%s) : %s %s", e.status_code, e, e.errors)
        if e.status_code == 422 and e.errors:
            raise PaiementImpossible("Informations refusées par le service de paiement : " + ", ".join(e.errors.keys()))
        if e.status_code is None and "CHARIOW_API_KEY" in str(e):
            raise PaiementImpossible("Paiement indisponible : le serveur n'est pas encore configuré (code C1).")
        if e.status_code == 401:
            raise PaiementImpossible("Paiement indisponible : configuration du service de paiement refusée (code C2).")
        if e.status_code == 404:
            raise PaiementImpossible("Paiement indisponible : formule introuvable chez le service de paiement (code C3).")
        if e.status_code is None:
            raise PaiementImpossible("Service de paiement injoignable pour le moment. Réessaie dans un instant (code C4).")
        raise PaiementImpossible(f"Le paiement n'a pas pu démarrer (code C5-{e.status_code}). Réessaie dans un instant.")

    step = data.get("step")
    payment = data.get("payment") or {}
    if step == "payment" and payment.get("checkout_url"):
        paiement.checkout_url = payment["checkout_url"]
        paiement.transaction_id = payment.get("transaction_id") or ""
        paiement.save(update_fields=["checkout_url", "transaction_id", "maj_le"])
        return paiement

    paiement.statut = "ECHEC"; paiement.note = f"Réponse inattendue : step={step} {data.get('message')}"; paiement.save()
    if step == "already_purchased":
        raise PaiementImpossible("Le service de paiement indique que tu as déjà acheté cette formule. "
                                 "Écris-nous à aide@treffcommunication.tech.")
    raise PaiementImpossible("Réponse inattendue du service de paiement.")


def _rattraper_pulse(paiement):
    """
    Si le webhook de CE paiement est déjà reçu mais pas encore traité (Celery arrêté ou en retard),
    on le traite tout de suite. Le webhook signé reste la seule source : on ne fait que l'exécuter plus tôt.
    """
    if paiement.statut != "EN_ATTENTE":
        return paiement
    for pulse in PulseChariow.objects.filter(traite=False).order_by("recu_le"):
        meta = ((pulse.corps or {}).get("sale") or {}).get("custom_metadata") or {}
        if meta.get("paiement_ref") == paiement.reference:
            try:
                traiter_pulse.apply(args=[pulse.pk])  # exécution immédiate, dans ce processus
            except Exception as e:  # noqa: BLE001
                log.warning("Rattrapage du Pulse %s impossible : %s", pulse.delivery_id, e)
    paiement.refresh_from_db()
    return paiement


def statut_pour_page_attente(paiement):
    """Traduit le statut Chariow pour la page d'attente du site (même format que l'ancienne gateway)."""
    paiement = _rattraper_pulse(paiement)
    if paiement.statut == "PAYE":
        abo = paiement.professional_profile.abonnement
        return {"status": "SUCCESSFUL", "message": f"Offre {paiement.offre.nom} activée",
                "expire_le": abo.date_fin.strftime("%d/%m/%Y"), "jours_restants": abo.jours_restants}
    if paiement.statut in ("ECHEC", "ABANDON"):
        return {"status": "FAILED"}
    if paiement.statut == "ANOMALIE":
        return {"status": "REVIEW"}
    return {"status": "PENDING"}


@csrf_exempt
@require_POST
def chariow_pulse(request):
    """
    Webhook Chariow. Ordre : signature (401 si invalide) -> dédoublonnage sur x-pulse-delivery-id
    -> enregistrement -> 200 immédiat -> traitement Celery après commit.
    """
    corps_brut = request.body  # octets exacts, AVANT tout parsing
    if not chariow.signature_valide(corps_brut, request.headers.get("x-chariow-signature", "")):
        log.warning("Pulse Chariow refusé : signature invalide")
        return JsonResponse({"error": "invalid signature"}, status=401)

    try:
        corps = json.loads(corps_brut.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid json"}, status=400)

    delivery_id = request.headers.get("x-pulse-delivery-id")
    evenement = request.headers.get("x-pulse-event") or corps.get("event", "")
    if not delivery_id:
        # Test envoyé depuis le tableau de bord Chariow : pas d'identifiant de livraison -> on ne traite pas
        log.info("Pulse de test reçu (%s) : signature OK, non traité.", evenement)
        return JsonResponse({"ok": True, "test": True})

    try:
        with transaction.atomic():
            pulse = PulseChariow.objects.create(
                delivery_id=delivery_id, pulse_id=request.headers.get("x-pulse-id", ""),
                evenement=evenement, corps=corps)
            transaction.on_commit(lambda: _lancer(pulse.pk))
    except IntegrityError:
        return JsonResponse({"ok": True, "duplicate": True})  # déjà reçu : Chariow réessaie, on confirme
    return JsonResponse({"ok": True})


def chariow_retour(request):
    """Page vue après le paiement. Elle n'active rien : seul le Pulse signé fait foi."""
    html = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Paiement reçu · Dress'Matter</title>
<style>body{margin:0;font-family:system-ui,sans-serif;background:#f8f5f0;color:#1d1a24;display:flex;min-height:100vh;
align-items:center;justify-content:center;text-align:center;padding:24px}.c{max-width:420px}
h1{font-size:24px;margin:16px 0 8px}p{color:#5d5866;line-height:1.5}.o{font-size:56px}</style></head>
<body><div class="c"><div class="o">🧵</div><h1>Merci !</h1>
<p>Ton paiement est en cours de confirmation. Retourne dans l'application Dress'Matter :
ton abonnement s'activera automatiquement dans quelques instants.</p></div></body></html>"""
    return HttpResponse(html)
