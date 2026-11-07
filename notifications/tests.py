from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import Notification


class HistoriqueNotificationsTests(APITestCase):
    def test_lues_gardees_7_jours(self):
        u = User.objects.create_user('notif_u', 'n@x.ci', 'x')
        self.client.force_authenticate(u)
        lue = Notification.objects.create(user=u, title='Lue', message='m', is_read=True)
        Notification.objects.create(user=u, title='Non lue', message='m')
        vieille = Notification.objects.create(user=u, title='Vieille', message='m', is_read=True)
        Notification.objects.filter(pk=vieille.pk).update(created_at=timezone.now() - timedelta(days=8))

        r = self.client.get('/api/v1/notifications/')
        titres = [n['title'] for n in r.data]
        self.assertEqual(sorted(titres), ['Lue', 'Non lue'])
        self.assertTrue(next(n for n in r.data if n['id'] == lue.id)['is_read'])

        self.client.post('/api/v1/notifications/mark-read/')
        r = self.client.get('/api/v1/notifications/')
        self.assertEqual(len(r.data), 2)  # toujours là après lecture
        self.assertEqual(self.client.get('/api/v1/notifications/unread-count/').data['unread_count'], 0)
