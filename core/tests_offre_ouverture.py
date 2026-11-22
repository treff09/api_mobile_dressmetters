import datetime
from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from core.models import Abonnement, AppConfiguration, ProfessionalProfile, quota_commandes

User = get_user_model()


class OffreOuvertureTests(TestCase):
    def setUp(self):
        AppConfiguration.objects.create(offre_ouverture_debut=datetime.date(2026, 11, 1),
                                        offre_ouverture_fin=datetime.date(2026, 12, 31), offre_ouverture_jours=30)

    def pro(self, nom, inscrit_le=None):
        u = User.objects.create_user(nom, f'{nom}@x.com', 'x')
        if inscrit_le:
            User.objects.filter(pk=u.pk).update(date_joined=timezone.make_aware(datetime.datetime.combine(inscrit_le, datetime.time(10))))
            u.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            p = ProfessionalProfile.objects.create(user=u, nom_entreprise=nom, numero_telephone=f"07{abs(hash(nom)) % 10**8:08d}")
        p.refresh_from_db()
        return p

    def test_compte_dans_la_periode(self):
        p = self.pro('awa', datetime.date(2026, 12, 15))
        abo = Abonnement.objects.get(professional_profile=p)
        self.assertGreaterEqual((abo.date_fin - timezone.now()).days, 29)
        self.assertTrue(p.offre_ouverture_recue)
        self.assertTrue(quota_commandes(p)['premium'])

    def test_compte_hors_periode(self):
        p = self.pro('ancien', datetime.date(2026, 10, 20))
        self.assertFalse(Abonnement.objects.filter(professional_profile=p).exists())
        p2 = self.pro('tard', datetime.date(2027, 1, 1))
        self.assertFalse(Abonnement.objects.filter(professional_profile=p2).exists())

    def test_offre_desactivee(self):
        AppConfiguration.objects.update(offre_ouverture_active=False)
        p = self.pro('kofi', datetime.date(2026, 11, 20))
        self.assertFalse(Abonnement.objects.filter(professional_profile=p).exists())

    def test_rattrapage_une_seule_fois(self):
        AppConfiguration.objects.update(offre_ouverture_active=False)
        p = self.pro('deja', datetime.date(2026, 11, 5))
        AppConfiguration.objects.update(offre_ouverture_active=True)
        call_command('offre_ouverture', stdout=StringIO())
        fin1 = Abonnement.objects.get(professional_profile=p).date_fin
        call_command('offre_ouverture', stdout=StringIO())   # 2e passage : rien de plus
        self.assertEqual(Abonnement.objects.get(professional_profile=p).date_fin, fin1)

    def test_deja_abonne_jours_ajoutes(self):
        AppConfiguration.objects.update(offre_ouverture_active=False)
        p = self.pro('paye', datetime.date(2026, 11, 10))
        fin = timezone.now() + datetime.timedelta(days=10)
        Abonnement.objects.create(professional_profile=p, date_fin=fin)
        AppConfiguration.objects.update(offre_ouverture_active=True)
        call_command('offre_ouverture', stdout=StringIO())
        self.assertEqual((Abonnement.objects.get(professional_profile=p).date_fin - fin).days, 30)
