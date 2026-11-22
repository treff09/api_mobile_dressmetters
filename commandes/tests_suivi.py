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
        Abonnement.objects.filter(professional_profile=self.pro).delete()
        # Parrain NON abonné : pas de bonus
        self.assertFalse(recompenser_parrain(filleul))
        self.assertFalse(Abonnement.objects.filter(professional_profile=self.pro).exists())
        # Parrain abonné : +30 jours sur SON abonnement, une seule fois
        fin = timezone.now() + timedelta(days=10)
        Abonnement.objects.create(professional_profile=self.pro, date_fin=fin)
        self.assertTrue(recompenser_parrain(filleul)); self.assertFalse(recompenser_parrain(filleul))
        abo = Abonnement.objects.get(professional_profile=self.pro)
        self.assertGreater(abo.date_fin, fin + timedelta(days=29))
        self.assertTrue(code)


class EssayageEtDiffusionTests(SuiviTests):
    def test_essayage_deplace_et_annule(self):
        url = f'/api/v1/commandes/{self.c.id}/essayage/'
        d1 = (timezone.now() + timedelta(days=3)).isoformat()
        d2 = (timezone.now() + timedelta(days=4)).isoformat()
        self.api_pro.patch(url, {'date_essayage': d1}, format='json')
        self.api_pro.patch(url, {'date_essayage': d1}, format='json')   # même date : rien
        self.api_pro.patch(url, {'date_essayage': d2}, format='json')
        self.api_pro.patch(url, {'date_essayage': None}, format='json')
        titres = list(Notification.objects.filter(user=self.cu, commande_id=self.c.id).values_list('title', flat=True))
        self.assertEqual(titres.count("Rendez-vous d'essayage"), 1)
        self.assertIn("Essayage déplacé", titres)
        self.assertIn("Essayage annulé", titres)

    def test_message_admin_cible_et_telephones(self):
        from unittest import mock
        from core.models import AppConfiguration
        cfg = AppConfiguration.objects.create()
        with mock.patch('core.push.envoyer_push_masse', return_value=1) as push, \
             self.captureOnCommitCallbacks(execute=True):
            cfg.global_title = 'Nouveauté'; cfg.global_message = 'Bonjour les couturiers'
            cfg.destinataires = 'COUTURIERS'; cfg.send_to_all_now = True; cfg.save()
        self.assertTrue(Notification.objects.filter(user=self.pu, title='Nouveauté').exists())
        self.assertFalse(Notification.objects.filter(user=self.cu, title='Nouveauté').exists())
        self.assertEqual(push.call_args[0][0], [self.pu.id])
        cfg.refresh_from_db(); self.assertFalse(cfg.send_to_all_now)


class EnvoiCibleTests(SuiviTests):
    def test_personne_choisie_et_groupe(self):
        from unittest import mock
        from core.models import EnvoiMessage
        with mock.patch('core.push.envoyer_push_masse', return_value=1) as push, \
             self.captureOnCommitCallbacks(execute=True):
            m = EnvoiMessage.objects.create(titre='Coucou', message='Juste pour toi', cible='PERSONNES')
            m.personnes.set([self.cu]); m.envoyer()
        self.assertTrue(Notification.objects.filter(user=self.cu, title='Coucou').exists())
        self.assertFalse(Notification.objects.filter(user=self.pu, title='Coucou').exists())
        self.assertEqual(push.call_args[0][0], [self.cu.id])
        m.refresh_from_db(); self.assertIsNotNone(m.envoye_le)
        # renvoyer ne double pas
        with self.captureOnCommitCallbacks(execute=True):
            m.envoyer()
        self.assertEqual(Notification.objects.filter(title='Coucou').count(), 1)
        from core.tasks_suivi import destinataires_ids
        self.assertEqual(destinataires_ids('COUTURIERS_GRATUITS'), [self.pu.id])
        self.assertEqual(destinataires_ids('COUTURIERS_PREMIUM'), [])

    def test_admin_formulaire(self):
        from django.contrib.auth import get_user_model
        admin_u = get_user_model().objects.create_superuser('adm', 'adm@x.ci', 'x12345')
        self.client.force_login(admin_u)
        r = self.client.get('/admin/core/enviomessage/add/'.replace('envio', 'envoi'))
        self.assertEqual(r.status_code, 200)
