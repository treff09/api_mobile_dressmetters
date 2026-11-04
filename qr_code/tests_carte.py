import io
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient
from core.models import ProfessionalProfile, ClientProfile, ModeleDisponible, TypeVetement

User = get_user_model()


def png(nom):
    b = io.BytesIO(); Image.new('RGB', (10, 10), 'red').save(b, 'PNG')
    return SimpleUploadedFile(nom, b.getvalue(), content_type='image/png')


class CarteEtVuesTests(TestCase):
    def setUp(self):
        self.tv = TypeVetement.objects.create(nom='Robe')
        def pro(n, lat, lng, quartier, modele=True):
            u = User.objects.create_user(n, f'{n}@x.ci', 'x12345')
            p = ProfessionalProfile.objects.create(user=u, nom_entreprise=n, numero_telephone=f'07{len(n)}{lat}'[:15],
                                                   latitude=lat, longitude=lng, quartier=quartier, ville='Abidjan')
            if modele:
                ModeleDisponible.objects.create(professional_profile=p, type_vetement=self.tv, nom='M', price=1000)
            return p
        self.cocody = pro('Cocody', 5.36, -3.98, 'Cocody')
        self.yop = pro('Yopougon', 5.34, -4.09, 'Yopougon')
        self.vide = pro('SansModele', 5.36, -3.98, 'Cocody', modele=False)
        self.loin = pro('Bouake', 7.69, -5.03, 'Commerce')
        cu = User.objects.create_user('cli', 'cli@x.ci', 'x12345')
        ClientProfile.objects.create(user=cu, nom='C', prenom='C')
        self.api = APIClient(); self.api.force_authenticate(cu)

    def test_autour_de_moi(self):
        r = self.api.get('/api/v1/qrcode/carte/', {'lat': 5.36, 'lng': -3.98, 'rayon_km': 5})
        noms = [x['nom_entreprise'] for x in r.data]
        self.assertEqual(noms, ['Cocody'])           # sans modèle et trop loin exclus
        r = self.api.get('/api/v1/qrcode/carte/', {'lat': 5.36, 'lng': -3.98, 'rayon_km': 20})
        self.assertEqual([x['nom_entreprise'] for x in r.data], ['Cocody', 'Yopougon'])

    def test_zone_saisie(self):
        r = self.api.get('/api/v1/qrcode/carte/', {'zone': 'yopou'})
        self.assertEqual([x['nom_entreprise'] for x in r.data], ['Yopougon'])

    def test_catalogue_sans_qr(self):
        r = self.api.get(f'/api/v1/qrcode/couturiers/{self.cocody.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['modeles_disponibles']), 1)
        self.assertEqual(r.data['couturier']['quartier'], 'Cocody')

    def test_trois_vues_modele(self):
        api = APIClient(); api.force_authenticate(self.cocody.user)
        r = api.post('/api/v1/core/modeles/add/', {
            'type_vetement': self.tv.id, 'nom': 'Boubou', 'price': '5000', 'acompte': '0',
            'image': png('f.png'), 'image_cote': png('c.png'), 'image_dos': png('d.png')}, format='multipart')
        self.assertIn(r.status_code, (200, 201), r.data)
        m = ModeleDisponible.objects.get(nom='Boubou')
        self.assertTrue(m.image_cote and m.image_dos)
        r = api.patch(f'/api/v1/core/modeles/{m.id}/update/', {'retirer_vues': 'dos'}, format='multipart')
        self.assertIn(r.status_code, (200, 201), r.data)
        m.refresh_from_db(); self.assertFalse(m.image_dos); self.assertTrue(m.image_cote)
        r = self.api.get(f'/api/v1/qrcode/couturiers/{self.cocody.id}/')
        boubou = [x for x in r.data['modeles_disponibles'] if x['nom'] == 'Boubou'][0]
        self.assertTrue(boubou['image_cote']); self.assertIsNone(boubou['image_dos'])
