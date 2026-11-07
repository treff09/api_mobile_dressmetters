from django.test import SimpleTestCase
from core.devise import format_montant


class DeviseTests(SimpleTestCase):
    def test_formats(self):
        self.assertEqual(format_montant(15000, 'XOF'), '15 000 FCFA')
        self.assertEqual(format_montant(25, 'EUR'), '25,00 €')
        self.assertEqual(format_montant(1250.5, 'USD'), '$1 250.50')
        self.assertEqual(format_montant(None, None), '0 FCFA')


from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from core.models import ProfessionalProfile


class ChoixDeviseTests(APITestCase):
    def test_premiere_connexion_puis_choix(self):
        u = User.objects.create_user('pro_dev', 'pro_dev@x.ci', 'x')
        ProfessionalProfile.objects.create(user=u, nom_entreprise='Atelier', numero_telephone='0700000099')
        self.client.force_authenticate(u)
        r = self.client.get('/api/v1/accounts/profile-type/')
        self.assertEqual(r.data['devise'], 'XOF'); self.assertFalse(r.data['devise_confirmee'])
        r = self.client.put('/api/v1/accounts/personal-info/', {'devise': 'EUR'}, format='json')
        self.assertEqual(r.status_code, 200)
        r = self.client.get('/api/v1/accounts/profile-type/')
        self.assertEqual(r.data['devise'], 'EUR'); self.assertTrue(r.data['devise_confirmee'])
        r = self.client.put('/api/v1/accounts/personal-info/', {'devise': 'ZZZ'}, format='json')
        self.assertEqual(r.status_code, 400)
