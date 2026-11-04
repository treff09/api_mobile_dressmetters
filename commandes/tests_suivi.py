from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (Abonnement, AppareilPush, ClientProfile, Commande, Notification, ProfessionalProfile)

User = get_user_model()


class SuiviTests(TestCase):
    def setUp(self):
        self.pu = User.objects.create_user('pro', 'p@x.ci', 'x12345')
        self.pro = ProfessionalProfile.objects.create(user=self.pu, nom_entreprise='Atelier Awa', numero_telephone='0700000009')
        self.cu = User.objects.create_user('cli', 'c@x.ci', 'x12345')
        self.cli = ClientProfile.objects.create(user=self.cu, nom='K', prenom='Ama')
        self.c = Commande.objects.create(client_profile=self.cli, professional_profile=self.pro,
                                         total_commande=Decimal('20000'), reste_a_payer=Decimal('20000'),
                                         date_livraison=timezone.now() + timedelta(days=1))
        self.api_pro = APIClient(); self.api_pro.force_authenticate(self.pu)
        self.api_cli = APIClient(); self.api_cli.force_authenticate(self.cu)

    def test_etapes_et_notifications(self):
        r = self.api_pro.patch(f'/api/v1/commandes/{self.c.id}/etape/', {'etape': 'COUTURE'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.cu, commande_id=self.c.id).exists())
        # le client ne peut pas changer l'étape
        self.assertEqual(self.api_cli.patch(f'/api/v1/commandes/{self.c.id}/etape/', {'etape': 'PRETE'}, format='json').status_code, 403)
        # ni le statut
        self.assertEqual(self.api_cli.patch(f'/api/v1/commandes/update-status/{self.c.id}/', {'statut': 'Terminée'}, format='json').status_code, 403)

    def test_paiements_et_relance(self):
        r = self.api_pro.post(f'/api/v1/commandes/{self.c.id}/paiements/', {'montant': '5000', 'moyen': 'MOBILE_MONEY'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.c.refresh_from_db()
        self.assertEqual(self.c.reste_a_payer, Decimal('15000')); self.assertEqual(self.c.statut_paiement, 'ACOMPTE_PAYE')
        self.assertEqual(self.api_pro.post(f'/api/v1/commandes/{self.c.id}/relancer/').status_code, 200)
        self.assertEqual(self.api_pro.post(f'/api/v1/commandes/{self.c.id}/relancer/').status_code, 429)
        pid = r.data['paiements'][0]['id']
        self.api_pro.delete(f'/api/v1/commandes/{self.c.id}/paiements/{pid}/')
        self.c.refresh_from_db(); self.assertEqual(self.c.reste_a_payer, Decimal('20000'))

    def test_avis_apres_livraison(self):
        url = f'/api/v1/commandes/{self.c.id}/avis/'
        self.assertEqual(self.api_cli.post(url, {'note': 5}, format='json').status_code, 400)  # pas encore livrée
        self.api_pro.patch(f'/api/v1/commandes/update-status/{self.c.id}/', {'statut': 'Terminée'}, format='json')
        self.assertEqual(self.api_cli.post(url, {'note': 5, 'commentaire': 'Top'}, format='json').status_code, 201)
        r = self.api_cli.get(f'/api/v1/commandes/couturiers/{self.pro.id}/avis/')
        self.assertEqual(r.data['moyenne'], 5); self.assertEqual(r.data['nombre'], 1)
        detail = self.api_cli.get('/api/v1/commandes/client/').data[0]
        self.assertEqual(detail['avis']['note'], 5); self.assertEqual(detail['etape'], 'LIVREE')

    def test_rappels_echeances(self):
        from core.tasks_suivi import rappels_echeances
        rappels_echeances(); rappels_echeances()  # 2e passage : pas de doublon
        self.assertEqual(Notification.objects.filter(user=self.pu, title='Livraison proche').count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.cu, title='Ta commande arrive').count(), 1)

    def test_tableau_de_bord_et_appareil(self):
        self.api_pro.post(f'/api/v1/commandes/{self.c.id}/paiements/', {'montant': '3000'}, format='json')
        r = self.api_pro.get('/api/v1/commandes/tableau-de-bord/')
        self.assertEqual(r.data['commandes_mois'], 1); self.assertEqual(Decimal(r.data['recu_mois']), Decimal('3000'))
        self.api_cli.post('/api/v1/commandes/appareils/', {'token': 'abc', 'plateforme': 'android'}, format='json')
        self.assertTrue(AppareilPush.objects.filter(user=self.cu, token='abc').exists())

    def test_parrainage(self):
        code = self.api_pro.get('/api/v1/commandes/parrainage/').data['code']
        u2 = User.objects.create_user('pro2', 'p2@x.ci', 'x12345')
        filleul = ProfessionalProfile.objects.create(user=u2, nom_entreprise='Filleul', numero_telephone='0700000010', parrain=self.pro)
        from commandes.views_suivi import recompenser_parrain
        self.assertTrue(recompenser_parrain(filleul)); self.assertFalse(recompenser_parrain(filleul))
        abo = Abonnement.objects.get(professional_profile=self.pro)
        self.assertGreater(abo.date_fin, timezone.now() + timedelta(days=29))
        self.assertTrue(code)
