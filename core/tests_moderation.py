from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import (AvisCouturier, Blocage, ClientProfile, Commande, ProfessionalProfile, Signalement)


class ModerationTests(APITestCase):
    def setUp(self):
        self.pu = User.objects.create_user('pro_m', 'pm@x.ci', 'x')
        self.pro = ProfessionalProfile.objects.create(user=self.pu, nom_entreprise='Atelier', numero_telephone='0700000077')
        self.cus = []
        self.avis = None
        for i in range(3):
            u = User.objects.create_user(f'cli_m{i}', f'cm{i}@x.ci', 'x')
            cli = ClientProfile.objects.create(user=u, nom='K', prenom=f'C{i}')
            c = Commande.objects.create(client_profile=cli, professional_profile=self.pro)
            a = AvisCouturier.objects.create(commande=c, professional_profile=self.pro, client_profile=cli, note=1, commentaire='nul')
            self.cus.append(u)
            self.avis = self.avis or a

    def test_signaler_et_bloquer(self):
        self.client.force_authenticate(self.pu)
        r = self.client.post('/api/v1/core/signaler/', {'type': 'avis', 'objet_id': self.avis.id,
                                                        'motif': 'insulte', 'bloquer': True}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Signalement.objects.filter(objet_id=self.avis.id).exists())
        self.assertTrue(Blocage.objects.filter(auteur=self.pu, bloque=self.cus[0]).exists())
        # l'avis de la personne bloquée disparaît pour celui qui a bloqué
        r = self.client.get(f'/api/v1/commandes/couturiers/{self.pro.id}/avis/')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(self.avis.id, [a['id'] for a in r.data['avis']])
        self.assertEqual(len(self.client.get('/api/v1/core/bloquer/').data), 1)
        self.client.delete('/api/v1/core/bloquer/', {'user_id': self.cus[0].id}, format='json')
        self.assertFalse(Blocage.objects.exists())

    def test_trois_signalements_masquent_l_avis(self):
        for u in self.cus:
            self.client.force_authenticate(u)
            self.client.post('/api/v1/core/signaler/', {'type': 'avis', 'objet_id': self.avis.id}, format='json')
        self.avis.refresh_from_db()
        self.assertFalse(self.avis.visible)
