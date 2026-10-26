from io import StringIO
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase


class NettoyerSeedTests(TestCase):
    def test_aperçu_puis_suppression(self):
        User.objects.create_user('client_seed_001', 'client_seed_001@seed.ci', 'x')
        User.objects.create_user('test_client', 'test.client@treffcommunication.tech', 'x')
        User.objects.create_user('vraie', 'awa@gmail.com', 'x')
        out = StringIO(); call_command('nettoyer_seed', stdout=out)
        self.assertEqual(User.objects.count(), 3)
        call_command('nettoyer_seed', '--confirmer', stdout=StringIO())
        self.assertEqual(sorted(User.objects.values_list('username', flat=True)), ['test_client', 'vraie'])
