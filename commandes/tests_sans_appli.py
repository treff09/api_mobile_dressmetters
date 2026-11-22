from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from core.models import ClientProfile, Commande, MesureClient, ProfessionalProfile, PersonneMesuree

User = get_user_model()


class SansAppliTests(TestCase):
    def setUp(self):
        self.pro_user = User.objects.create_user('pro', 'pro@x.com', 'x')
        self.pro = ProfessionalProfile.objects.create(user=self.pro_user, nom_entreprise="Atelier Awa", numero_telephone="0700000001")
        self.api = APIClient(); self.api.force_authenticate(self.pro_user)
        from core.models import ModeleDisponible, TypeVetement
        self.type = TypeVetement.objects.create(nom="Boubou")
        self.modele = ModeleDisponible.objects.create(professional_profile=self.pro, type_vetement=self.type,
                                                      nom="Boubou bazin", price=25000, acompte=10000)

    def creer(self, tel="+225 07 11 22 33 44", **extra):
        d = {"prenom": "Koffi", "nom": "Yao", "telephone": tel, "description": "Boubou bazin", "modele_disponible": self.modele.id,
             "total": "25000", "acompte": "10000", "date_livraison": "2026-12-20",
             "mesures": [{"nom": "Tour de taille", "valeur": 82}, {"nom": "Longueur", "valeur": "110,5"}]}
        d.update(extra)
        return self.api.post('/api/v1/commandes/sans-appli/', d, format='json')

    def test_parcours_complet(self):
        r = self.creer(); self.assertEqual(r.status_code, 201, r.data)
        self.assertIn('/s/', r.data['lien_suivi']); self.assertIn('wa.me/2250711223344', r.data['lien_whatsapp'])
        c = Commande.objects.get(pk=r.data['id'])
        self.assertTrue(c.client_profile.invite); self.assertEqual(c.articles.first().mesures_figees.count(), 2)
        # 2e commande, même numéro écrit autrement : même fiche client
        r2 = self.creer(tel="0711223344"); c2 = Commande.objects.get(pk=r2.data['id'])
        self.assertEqual(c2.client_profile_id, c.client_profile_id)
        # Page publique
        page = self.client.get(f'/s/{c.lien_suivi}/')
        self.assertEqual(page.status_code, 200); self.assertContains(page, "Atelier Awa"); self.assertContains(page, "Commande reçue")
        self.assertEqual(self.client.get('/s/inconnu/').status_code, 404)
        # Le client s'inscrit, possède déjà une mesure plus ancienne
        cu = User.objects.create_user('koffi', 'k@x.com', 'x'); vrai = ClientProfile.objects.create(user=cu, prenom="Koffi")
        api_c = APIClient(); api_c.force_authenticate(cu)
        r3 = api_c.post('/api/v1/commandes/recuperer/', {"lien": r.data['lien_suivi']}, format='json')
        self.assertEqual(r3.status_code, 200, r3.data); self.assertEqual(r3.data['commandes'], 2)
        self.assertEqual(Commande.objects.filter(client_profile=vrai).count(), 2)
        moi = PersonneMesuree.moi(vrai)
        self.assertEqual(MesureClient.objects.filter(client_profile=vrai, personne=moi).count(), 2)
        self.assertFalse(ClientProfile.objects.filter(invite=True).exists())
        self.assertEqual(vrai.__class__.objects.get(pk=vrai.pk).numero_telephone, "+2250711223344")
        # Commande déjà rattachée : un autre compte ne peut pas la prendre
        autre = User.objects.create_user('autre', 'a@x.com', 'x'); ClientProfile.objects.create(user=autre)
        api_a = APIClient(); api_a.force_authenticate(autre)
        self.assertEqual(api_a.post('/api/v1/commandes/recuperer/', {"lien": c.lien_suivi}, format='json').status_code, 403)
        # Liste pro : nom lisible, pas « invite_… »
        lst = self.api.get(f'/api/v1/commandes/{c.id}/lien-suivi/'); self.assertEqual(lst.status_code, 200)

    def test_commande_pour_un_enfant(self):
        # Le parent a déjà l'appli et ses propres mesures (« Moi »)
        from core.models import LibelleMesure
        cu = User.objects.create_user('maman', 'm@x.com', 'x'); vrai = ClientProfile.objects.create(user=cu, prenom="Awa")
        lib = LibelleMesure.objects.create(nom="Tour de taille")
        MesureClient.objects.create(client_profile=vrai, personne=PersonneMesuree.moi(vrai), libelle=lib, valeur=70)
        r = self.creer(prenom="Awa", pour="Junior", genre="H", mesures=[{"nom": "Tour de taille", "valeur": 55}])
        self.assertEqual(r.status_code, 201, r.data)
        c = Commande.objects.get(pk=r.data['id'])
        self.assertEqual(c.articles.first().personne_nom, "Junior")
        self.assertContains(self.client.get(f'/s/{c.lien_suivi}/'), "Junior")
        api_c = APIClient(); api_c.force_authenticate(cu)
        self.assertEqual(api_c.post('/api/v1/commandes/recuperer/', {"lien": c.lien_suivi}, format='json').status_code, 200)
        moi = PersonneMesuree.moi(vrai); junior = vrai.personnes.get(prenom="Junior")
        self.assertEqual(MesureClient.objects.get(personne=moi, libelle=lib).valeur, 70)      # les siennes : intactes
        self.assertEqual(MesureClient.objects.get(personne=junior, libelle__nom="Tour de taille").valeur, 55)   # celles du fils
        self.assertEqual(junior.genre, 'H')
        self.assertEqual(Commande.objects.get(pk=c.pk).articles.first().personne_id, junior.id)

    def test_facture(self):
        r = self.creer(); c = Commande.objects.get(pk=r.data['id'])
        self.assertEqual(self.api.get(f'/api/v1/commandes/{c.id}/facture/').status_code, 400)  # pas livrée
        self.assertEqual(self.client.get(f'/s/{c.lien_suivi}/facture/').status_code, 302)
        from core.models import PaiementCommande
        PaiementCommande.objects.create(commande=c, montant=25000, moyen='ESPECE')
        Commande.objects.filter(pk=c.pk).update(etape='LIVREE', montant_paye=25000, reste_a_payer=0)
        f = self.api.get(f'/api/v1/commandes/{c.id}/facture/')
        self.assertEqual(f.status_code, 200); self.assertIn('/facture/', f.data['lien_facture'])
        page = self.client.get(f'/s/{c.lien_suivi}/facture/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Boubou bazin"); self.assertContains(page, "PAYÉE"); self.assertContains(page, "Atelier Awa")
        self.assertContains(self.client.get(f'/s/{c.lien_suivi}/'), "Voir ma facture")
        # Un autre utilisateur ne peut pas demander la facture
        autre = User.objects.create_user('x2', 'x2@x.com', 'x'); a = APIClient(); a.force_authenticate(autre)
        self.assertEqual(a.get(f'/api/v1/commandes/{c.id}/facture/').status_code, 404)

    def test_facture_ancienne_commande(self):
        # Ancienne commande terminée avant l'existence des étapes, sans lien de suivi
        r = self.creer(); Commande.objects.filter(pk=r.data['id']).update(statut='Terminées', etape='RECUE', lien_suivi=None)
        f = self.api.get(f"/api/v1/commandes/{r.data['id']}/facture/")
        self.assertEqual(f.status_code, 200)
        self.assertEqual(self.client.get(f.data['lien_facture'].split('testserver')[-1]).status_code, 200)

    def test_refus(self):
        self.assertEqual(self.creer(tel="12").status_code, 400)
        self.assertEqual(self.creer(modele_disponible="").status_code, 400)   # ni type ni modèle
        self.assertEqual(self.creer(modele_disponible="", type_vetement=self.type.id).status_code, 400)  # pas de photo
        cu = User.objects.create_user('c2', 'c2@x.com', 'x'); ClientProfile.objects.create(user=cu)
        a = APIClient(); a.force_authenticate(cu)
        self.assertEqual(a.post('/api/v1/commandes/sans-appli/', {}, format='json').status_code, 403)
