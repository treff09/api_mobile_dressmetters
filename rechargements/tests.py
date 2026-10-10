import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Abonnement, OffreAbonnement, ProfessionalProfile

from . import chariow
from .models import PaiementChariow, PulseChariow
from .tasks import traiter_pulse

SECRET = "whsec_test123"


def signer(corps: bytes):
    return "sha256=" + hmac.new(SECRET.encode(), corps, hashlib.sha256).hexdigest()


@override_settings(CHARIOW_PULSE_SECRET=SECRET, CHARIOW_API_KEY="sk_test_x", CHARIOW_REDIRECT_URL="")
@override_settings(ALLOWED_HOSTS=["testserver", "dressmetter.stephaneboundaone.tech"])
class ChariowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pro", "pro@ex.com", "x")
        self.pro = ProfessionalProfile.objects.create(user=self.user, nom_entreprise="Atelier", nom="Traoré",
                                                      prenom="Moussa", numero_telephone="+2250700000001")
        self.mensuel = OffreAbonnement.objects.create(nom="Mensuel", prix=Decimal("5000"), duree_jours=30,
                                                      chariow_product_id="prd_mensuel")
        self.annuel = OffreAbonnement.objects.create(nom="Annuel", prix=Decimal("50000"), duree_jours=365,
                                                     chariow_product_id="prd_annuel")
        self.api = APIClient(); self.api.force_authenticate(self.user)

    # ---------- helpers ----------
    def paiement(self, offre=None, ref="DM-1"):
        offre = offre or self.mensuel
        return PaiementChariow.objects.create(reference=ref, professional_profile=self.pro, offre=offre,
                                              montant_attendu=offre.prix)

    def corps_vente(self, ref="DM-1", plan=None, user_id=None, montant=5000, event="successful.sale", sale_id="sal_1"):
        return {"event": event, "sale": {"id": sale_id, "amount": {"value": montant, "currency": "XOF"},
                "custom_metadata": {"user_id": str(user_id or self.user.id), "plan": str(plan or self.mensuel.id),
                                    "paiement_ref": ref}}}

    def envoyer(self, corps, delivery="del_1", signature=None):
        brut = json.dumps(corps, separators=(",", ":")).encode()
        headers = {"HTTP_X_CHARIOW_SIGNATURE": signature if signature is not None else signer(brut),
                   "HTTP_X_PULSE_EVENT": corps.get("event", "")}
        if delivery:
            headers["HTTP_X_PULSE_DELIVERY_ID"] = delivery
        with mock.patch("rechargements.views_chariow.traiter_pulse.delay", side_effect=lambda pk: traiter_pulse(pk)):
            with self.captureOnCommitCallbacks(execute=True):
                return self.client.post("/api/v1/subscription/chariow/pulse/", brut, content_type="application/json", **headers)

    # ---------- webhook ----------
    def test_signature_invalide_401(self):
        self.paiement()
        r = self.envoyer(self.corps_vente(), signature="sha256=deadbeef")
        self.assertEqual(r.status_code, 401)
        self.assertFalse(Abonnement.objects.exists())

    def test_signature_absente_401(self):
        r = self.envoyer(self.corps_vente(), signature="")
        self.assertEqual(r.status_code, 401)

    def test_vente_reussie_active_30_jours(self):
        self.paiement()
        r = self.envoyer(self.corps_vente())
        self.assertEqual(r.status_code, 200)
        abo = Abonnement.objects.get(professional_profile=self.pro)
        self.assertAlmostEqual((abo.date_fin - timezone.now()).total_seconds(), 30 * 86400, delta=60)
        p = PaiementChariow.objects.get(reference="DM-1")
        self.assertEqual(p.statut, "PAYE"); self.assertTrue(p.applique); self.assertEqual(p.sale_id, "sal_1")

    def test_annuel_365_jours_et_prolonge_si_actif(self):
        Abonnement.objects.create(professional_profile=self.pro, offre=self.mensuel, date_fin=timezone.now() + timedelta(days=10))
        self.paiement(self.annuel)
        self.envoyer(self.corps_vente(plan=self.annuel.id, montant=50000))
        abo = Abonnement.objects.get(professional_profile=self.pro)
        self.assertAlmostEqual((abo.date_fin - timezone.now()).total_seconds(), 375 * 86400, delta=60)

    def test_meme_livraison_dedoublonnee(self):
        self.paiement()
        self.envoyer(self.corps_vente(), delivery="del_X")
        r = self.envoyer(self.corps_vente(), delivery="del_X")
        self.assertEqual(r.status_code, 200); self.assertTrue(r.json().get("duplicate"))
        self.assertEqual(PulseChariow.objects.count(), 1)

    def test_deux_livraisons_meme_vente_pas_de_double_credit(self):
        self.paiement()
        self.envoyer(self.corps_vente(), delivery="del_A")
        fin1 = Abonnement.objects.get().date_fin
        self.envoyer(self.corps_vente(), delivery="del_B")  # rejeu manuel : nouvel id de livraison
        self.assertEqual(Abonnement.objects.get().date_fin, fin1)

    def test_metadonnees_incoherentes_pas_d_activation(self):
        self.paiement()
        self.envoyer(self.corps_vente(user_id=999))
        self.assertFalse(Abonnement.objects.exists())
        self.assertEqual(PaiementChariow.objects.get().statut, "ANOMALIE")

    def test_montant_insuffisant_pas_d_activation(self):
        self.paiement()
        self.envoyer(self.corps_vente(montant=100))
        self.assertFalse(Abonnement.objects.exists())
        self.assertEqual(PaiementChariow.objects.get().statut, "ANOMALIE")

    def test_evenement_test_sans_delivery_id(self):
        self.paiement()
        r = self.envoyer(self.corps_vente(), delivery=None)
        self.assertEqual(r.status_code, 200); self.assertTrue(r.json().get("test"))
        self.assertFalse(Abonnement.objects.exists())

    def test_vente_echouee(self):
        self.paiement()
        self.envoyer(self.corps_vente(event="failed.sale"))
        self.assertEqual(PaiementChariow.objects.get().statut, "ECHEC")
        self.assertFalse(Abonnement.objects.exists())

    def test_activation_directe_fermee(self):
        r = self.api.post("/api/v1/subscription/activate/", {"offre_id": self.mensuel.id}, format="json")
        self.assertEqual(r.status_code, 410)
        self.assertFalse(Abonnement.objects.exists())

    # ---------- parcours web (le paiement se fait sur le site) ----------
    def _rep_checkout(self):
        rep = mock.Mock(status_code=201)
        rep.json.return_value = {"data": {"step": "payment", "message": "ok", "purchase": {},
                                          "payment": {"checkout_url": "https://pay.chariow.com/x", "transaction_id": "trx_1"}}}
        return rep

    def test_web_payer_redirige_vers_chariow_sans_activer(self):
        self.client.force_login(self.user)
        with mock.patch("rechargements.chariow.requests.post", return_value=self._rep_checkout()) as post:
            r = self.client.post(f"/payments/payer/{self.annuel.id}/", {"phone_local": "0700000001"},
                                 HTTP_X_FORWARDED_FOR="41.66.10.20, 10.0.0.1", HTTP_HOST="dressmetter.stephaneboundaone.tech",
                                 secure=True)
        self.assertEqual(r.status_code, 302); self.assertEqual(r["Location"], "https://pay.chariow.com/x")
        body = post.call_args.kwargs["json"]
        p = PaiementChariow.objects.get()
        self.assertEqual(body["product_id"], "prd_annuel")
        self.assertEqual(body["phone"], {"number": "0700000001", "country_code": "CI"})
        self.assertEqual(body["customer_ip"], "41.66.10.20")
        self.assertEqual(body["custom_metadata"], {"user_id": str(self.user.id), "plan": str(self.annuel.id),
                                                   "paiement_ref": p.reference})
        self.assertEqual(body["redirect_url"], f"https://dressmetter.stephaneboundaone.tech/payments/attente/{p.reference}/")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer sk_test_x")
        self.assertFalse(Abonnement.objects.exists())

    def test_web_en_local_pas_d_adresse_locale_envoyee(self):
        self.client.force_login(self.user)
        with mock.patch("rechargements.chariow.requests.post", return_value=self._rep_checkout()) as post:
            self.client.post(f"/payments/payer/{self.mensuel.id}/", {"phone_local": "0700000001"})
        self.assertNotIn("redirect_url", post.call_args.kwargs["json"])   # CHARIOW_REDIRECT_URL vide en test

    def test_web_page_attente_n_active_rien_puis_reflete_le_webhook(self):
        self.client.force_login(self.user)
        p = self.paiement(ref="DM-W1")
        self.assertEqual(self.client.get("/payments/attente/DM-W1/").status_code, 200)
        r = self.client.get("/payments/confirmer/DM-W1/")
        self.assertEqual(r.json()["status"], "PENDING")
        self.assertFalse(Abonnement.objects.exists())          # le retour de page n'active pas
        self.envoyer(self.corps_vente(ref="DM-W1"))           # le webhook, si
        r = self.client.get("/payments/confirmer/DM-W1/")
        self.assertEqual(r.json()["status"], "SUCCESSFUL")

    def test_web_page_attente_rattrape_webhook_non_traite(self):
        self.client.force_login(self.user)
        self.paiement(ref="DM-W3")
        brut = json.dumps(self.corps_vente(ref="DM-W3"), separators=(",", ":")).encode()
        with mock.patch("rechargements.views_chariow.traiter_pulse.delay", side_effect=Exception("Celery arrêté")):
            with self.captureOnCommitCallbacks(execute=True):
                r = self.client.post("/api/v1/subscription/chariow/pulse/", brut, content_type="application/json",
                                     HTTP_X_CHARIOW_SIGNATURE=signer(brut), HTTP_X_PULSE_DELIVERY_ID="del_W3",
                                     HTTP_X_PULSE_EVENT="successful.sale")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Abonnement.objects.exists())            # Celery n'a rien fait
        r = self.client.get("/payments/confirmer/DM-W3/")
        self.assertEqual(r.json()["status"], "SUCCESSFUL")        # la page d'attente rattrape
        self.assertTrue(Abonnement.objects.get().est_actif)

    def test_web_already_purchased(self):
        self.client.force_login(self.user)
        rep = mock.Mock(status_code=200)
        rep.json.return_value = {"data": {"step": "already_purchased", "message": "déjà", "purchase": None, "payment": None}}
        with mock.patch("rechargements.chariow.requests.post", return_value=rep):
            r = self.client.post(f"/payments/payer/{self.mensuel.id}/", {"phone_local": "0700000001"})
        self.assertEqual(r.status_code, 200); self.assertContains(r, "déjà acheté")

    def test_web_paiement_d_un_autre_pro_inaccessible(self):
        autre = User.objects.create_user("autre", "a@ex.com", "x")
        ProfessionalProfile.objects.create(user=autre, nom_entreprise="B", numero_telephone="+2250700000009")
        self.paiement(ref="DM-W2")
        self.client.force_login(autre)
        self.assertEqual(self.client.get("/payments/confirmer/DM-W2/").status_code, 404)

    def test_api_app_ne_permet_pas_de_payer(self):
        r = self.api.post("/api/v1/subscription/chariow/checkout/", {"offre_id": self.mensuel.id}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_telephone(self):
        self.assertEqual(chariow.telephone_chariow("+225 07 00 00 00 01"), {"number": "0700000001", "country_code": "CI"})
        self.assertEqual(chariow.telephone_chariow("+33 6 12 34 56 78")["country_code"], "FR")
        self.assertIsNone(chariow.telephone_chariow("abc"))


class AccesPremiumTests(TestCase):
    """Les modèles en trop disparaissent dès la fin de l'abonnement (client et couturier)."""

    def setUp(self):
        from core.models import AppConfiguration, ModeleDisponible, TypeVetement
        self.user = User.objects.create_user("p2", "p2@ex.com", "x")
        self.pro = ProfessionalProfile.objects.create(user=self.user, nom_entreprise="A", numero_telephone="+2250700000002")
        tv = TypeVetement.objects.create(nom="Robe")
        for i in range(8):
            ModeleDisponible.objects.create(professional_profile=self.pro, type_vetement=tv, nom=f"M{i}", price=Decimal(1000))
        self.limite = AppConfiguration.limite_modeles_gratuits()

    def test_limite_sans_abonnement_et_tout_avec(self):
        from core.models import modeles_visibles
        self.assertEqual(len(modeles_visibles(self.pro)), min(8, self.limite))
        abo = Abonnement.objects.create(professional_profile=self.pro, date_fin=timezone.now() + timedelta(days=30))
        self.assertEqual(len(modeles_visibles(self.pro)), 8)
        abo.date_fin = timezone.now() - timedelta(seconds=1); abo.save()   # abonnement terminé
        self.assertEqual(len(modeles_visibles(self.pro)), min(8, self.limite))

