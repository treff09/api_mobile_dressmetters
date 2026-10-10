from datetime import timedelta
from unittest import mock
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from core.models import ProfessionalProfile, QRToken


class ScanTests(TestCase):
    def setUp(self):
        u = User.objects.create_user("pro", "p@e.com", "x")
        self.pro = ProfessionalProfile.objects.create(user=u, nom_entreprise="A", numero_telephone="+2250700000001")
        self.client_u = User.objects.create_user("cli", "c@e.com", "x")
        self.client.force_login(self.client_u)

    def scan(self, tok):
        return self.client.get(f"/api/v1/qrcode/access/{tok}/")

    def test_rescan_possible_pendant_5_minutes(self):
        QRToken.objects.create(professional_profile=self.pro, token="T1")
        self.assertEqual(self.scan("T1").status_code, 200)
        self.assertEqual(self.scan("T1").status_code, 200)          # rescan juste après
        t = QRToken.objects.get(token="T1")
        with mock.patch("django.utils.timezone.now", return_value=t.premier_scan_le + timedelta(minutes=4)):
            self.assertEqual(self.scan("T1").status_code, 200)      # 4 min après : toujours OK
        with mock.patch("django.utils.timezone.now", return_value=t.premier_scan_le + timedelta(minutes=6)):
            self.assertEqual(self.scan("T1").status_code, 400)      # 6 min après : expiré

    def test_non_scanne_expire_apres_5_minutes(self):
        t = QRToken.objects.create(professional_profile=self.pro, token="T2")
        with mock.patch("django.utils.timezone.now", return_value=t.created_at + timedelta(minutes=6)):
            self.assertEqual(self.scan("T2").status_code, 400)

    def test_permanent_reste(self):
        QRToken.objects.create(professional_profile=self.pro, token="DEMO", permanent=True)
        for _ in range(3):
            self.assertEqual(self.scan("DEMO").status_code, 200)
