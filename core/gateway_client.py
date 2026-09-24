"""
Client pour appeler la gateway de paiement (MTN MoMo / Wave / Orange Money).
Ce backend s'identifie auprès de la gateway avec sa propre clé API
(PAYMENT_GATEWAY_API_KEY), créée côté gateway dans /admin/ -> Payments ->
Client applications. L'appel se fait uniquement côté serveur (requests),
donc la clé n'est jamais exposée au navigateur.
"""

import uuid

import requests
from django.conf import settings


class GatewayError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _headers():
    return {
        "X-Api-Key": settings.PAYMENT_GATEWAY_API_KEY,
        "Content-Type": "application/json",
    }


def generate_order_id(prefix="ABO"):
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def initiate_payment(*, provider, amount, phone_number, order_id):
    """
    Appelle POST /api/payments/pay/ sur la gateway.
    Retourne le JSON : {"external_id", "status", "redirect_url"}
    """
    url = f"{settings.PAYMENT_GATEWAY_BASE_URL}/pay/"
    try:
        response = requests.post(
            url,
            headers=_headers(),
            json={
                "provider": provider,
                "amount": str(amount),
                "phone_number": phone_number,
                "order_id": order_id,
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise GatewayError(f"Gateway injoignable : {exc}") from exc

    if response.status_code not in (200, 202):
        raise GatewayError(
            f"Erreur gateway ({response.status_code})", status_code=response.status_code, payload=response.text
        )
    return response.json()


def check_status(order_id):
    """Appelle GET /api/payments/status/<order_id>/ sur la gateway."""
    url = f"{settings.PAYMENT_GATEWAY_BASE_URL}/status/{order_id}/"
    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as exc:
        raise GatewayError(f"Gateway injoignable : {exc}") from exc

    if not response.ok:
        raise GatewayError(
            f"Erreur gateway ({response.status_code})", status_code=response.status_code, payload=response.text
        )
    return response.json()