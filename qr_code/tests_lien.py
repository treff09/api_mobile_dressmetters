from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from core.models import ProfessionalProfile, QRToken


class LienPartageTests(TestCase):
    def setUp(self):
        u = get_user_model().objects.create_user(username='cout', email='c@x.ci', password='x12345')
        self.pro = ProfessionalProfile.objects.create(user=u, nom_entreprise='Atelier Awa', numero_telephone='0700000001')
        self.api = APIClient()
        self.api.force_authenticate(u)

    def test_lien_permanent_et_page(self):
        r = self.api.get('/api/v1/qrcode/lien-partage/')
        self.assertEqual(r.status_code, 200)
        code = r.data['code']
        self.assertIn(f'/c/{code}/', r.data['lien'])
        self.assertTrue(r.data['qr_png_base64'])
        # même lien la 2e fois
        self.assertEqual(self.api.get('/api/v1/qrcode/lien-partage/').data['code'], code)
        page = self.client.get(f'/c/{code}/', HTTP_USER_AGENT='Mozilla/5.0 (Linux; Android 14)')
        self.assertContains(page, 'Atelier Awa')
        self.assertContains(page, 'intent://c/' + code)
        # l'accès appli fonctionne et le lien ne s'use pas
        for _ in range(2):
            self.assertEqual(self.api.get(f'/api/v1/qrcode/access/{code}/').status_code, 200)
        # nouveau lien : l'ancien ne marche plus
        nouveau = self.api.get('/api/v1/qrcode/lien-partage/?nouveau=1').data['code']
        self.assertNotEqual(nouveau, code)
        self.assertContains(self.client.get(f'/c/{code}/'), 'Lien expiré')

    def test_assetlinks(self):
        self.assertEqual(self.client.get('/.well-known/assetlinks.json').json(), [])
