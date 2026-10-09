"""
Client Chariow (https://chariow.dev).

- creer_checkout() : POST /v1/checkout, renvoie la réponse « data » de Chariow.
- signature_valide() : vérifie l'en-tête x-chariow-signature d'un Pulse (webhook).
- telephone_chariow() : transforme « +2250700000001 » en {"number": "0700000001", "country_code": "CI"}.
- ip_client() : IP réelle de l'acheteur derrière Nginx.

Réglages (variables d'environnement / .env) :
    CHARIOW_API_KEY          clé API secrète (sk_live_… ou sk_test_…)
    CHARIOW_PULSE_SECRET     secret de signature du Pulse (whsec_…), PAS la clé API
    CHARIOW_REDIRECT_URL     page affichée après le paiement (facultatif)
"""
import hashlib
import hmac
import logging

import phonenumbers
import requests
from django.conf import settings

log = logging.getLogger(__name__)

API_URL = "https://api.chariow.com/v1"
TIMEOUT = 20


class ChariowError(Exception):
    def __init__(self, message, status_code=None, errors=None):
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or {}


def creer_checkout(*, product_id, email, prenom, nom, telephone, customer_ip, metadata, redirect_url=None):
    """Appelle POST /checkout. Renvoie le dict « data » (step, message, purchase, payment)."""
    if not settings.CHARIOW_API_KEY:
        raise ChariowError("CHARIOW_API_KEY n'est pas configurée sur le serveur.")
    body = {
        "product_id": product_id,
        "email": email,
        "first_name": (prenom or "Client")[:50],
        "last_name": (nom or "Dress'Matter")[:50],
        "phone": telephone,
        # Max 10 clés, valeurs ≤ 255 caractères, clés alphanumériques + « _ »
        "custom_metadata": {k: str(v)[:255] for k, v in metadata.items()},
    }
    if customer_ip:
        body["customer_ip"] = customer_ip
    if redirect_url:
        body["redirect_url"] = redirect_url
    try:
        r = requests.post(
            f"{API_URL}/checkout",
            json=body,
            headers={
                "Authorization": f"Bearer {settings.CHARIOW_API_KEY}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise ChariowError(f"Chariow injoignable : {e}")

    try:
        payload = r.json()
    except ValueError:
        payload = {}
    if r.status_code >= 400:
        log.warning("Chariow checkout %s : %s", r.status_code, r.text[:500])
        raise ChariowError(payload.get("message") or f"Erreur Chariow ({r.status_code})",
                           status_code=r.status_code, errors=payload.get("errors"))
    return payload.get("data") or {}


def signature_valide(corps_brut: bytes, entete: str) -> bool:
    """
    x-chariow-signature = "sha256=" + HMAC-SHA256(corps brut, secret du Pulse) en hexadécimal minuscule.
    Le corps doit être celui reçu, octet pour octet (jamais du JSON re-sérialisé).
    """
    secret = settings.CHARIOW_PULSE_SECRET
    if not secret or not entete:
        return False
    attendu = "sha256=" + hmac.new(secret.encode(), corps_brut, hashlib.sha256).hexdigest()
    recu = entete.strip()
    return len(recu) == len(attendu) and hmac.compare_digest(recu, attendu)


def telephone_chariow(numero: str, pays_defaut: str = "CI"):
    """'+225 07 00 00 00 01' -> {'number': '0700000001', 'country_code': 'CI'}. None si invalide."""
    if not numero:
        return None
    try:
        p = phonenumbers.parse(numero, pays_defaut)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(p):
        return None
    region = phonenumbers.region_code_for_number(p) or pays_defaut
    national = phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.NATIONAL)
    chiffres = "".join(ch for ch in national if ch.isdigit())
    return {"number": chiffres, "country_code": region}


def ip_client(request):
    """IP de l'acheteur : entrée la plus à gauche de X-Forwarded-For (Nginx), sinon REMOTE_ADDR."""
    cf = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf:
        return cf.strip()
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
