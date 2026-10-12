from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from core.models import (Abonnement, AppConfiguration, ClientProfile, Commande, Notification,
                         ProfessionalProfile, quota_commandes)


class QuotaCommandesTests(TestCase):
    def setUp(self):
        self.pro_u = User.objects.create_user("pro", "p@e.com", "x")
        self.pro = ProfessionalProfile.objects.create(user=self.pro_u, nom_entreprise="Atelier", numero_telephone="+2250700000001")
        cu = User.objects.create_user("cli", "c@e.com", "x")
        self.cli = ClientProfile.objects.create(user=cu, nom="K", prenom="A")
        AppConfiguration.objects.create(nb_commandes_mensuelles_gratuites=3)

    def cmd(self, quand=None):
        c = Commande.objects.create(client_profile=self.cli, professional_profile=self.pro, total_commande=Decimal(0))
        if quand:
            Commande.objects.filter(pk=c.pk).update(date_creation=quand)

    def test_limite_par_mois(self):
        for _ in range(2): self.cmd()
        self.assertEqual(quota_commandes(self.pro)['restantes'], 1)
        self.cmd()
        self.assertTrue(quota_commandes(self.pro)['atteinte'])

    def test_mois_precedent_ne_compte_pas(self):
        debut = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for _ in range(5): self.cmd(debut - timedelta(days=2))
        self.assertFalse(quota_commandes(self.pro)['atteinte'])

    def test_premium_illimite(self):
        for _ in range(5): self.cmd()
        Abonnement.objects.create(professional_profile=self.pro, date_fin=timezone.now() + timedelta(days=30))
        q = quota_commandes(self.pro)
        self.assertTrue(q['premium']); self.assertFalse(q['atteinte']); self.assertIsNone(q['limite'])

    def test_commande_refusee_et_couturier_prevenu_une_fois(self):
        from commandes.views import _prevenir_limite_atteinte
        for _ in range(3): self.cmd()
        _prevenir_limite_atteinte(self.pro, 3); _prevenir_limite_atteinte(self.pro, 3)
        self.assertEqual(Notification.objects.filter(user=self.pro_u, title="Limite de commandes atteinte").count(), 1)
        from rest_framework.test import APIClient
        api = APIClient(); api.force_authenticate(User.objects.get(username="cli"))
        r = api.post("/api/v1/commandes/add/", {"professional_profile": self.pro.id, "articles": []}, format="json")
        self.assertEqual(r.status_code, 403, r.content)
        self.assertEqual(r.json()["code"], "LIMITE_COMMANDES")
        self.assertEqual(Commande.objects.count(), 3)


class DeconnexionWebTests(TestCase):
    def test_bouton_deconnexion(self):
        u = User.objects.create_user("pw", "pw@e.com", "x")
        ProfessionalProfile.objects.create(user=u, nom_entreprise="B", numero_telephone="+2250700000005")
        self.client.force_login(u)
        page = self.client.get("/payments/recharge/")
        self.assertContains(page, "Se déconnecter")
        r = self.client.post("/accounts/web-logout/")
        self.assertRedirects(r, "/accounts/web-login/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/payments/recharge/").status_code, 302)   # plus connecté
