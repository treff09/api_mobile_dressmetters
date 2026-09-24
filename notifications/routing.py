from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # L'adresse devient : ws://127.0.0.1:8000/ws/notifications/ID_UTILISATEUR/
    # Exemple : ws://127.0.0.1:8000/ws/notifications/1/
    re_path(r'ws/notifications/(?P<user_id>\d+)/$', consumers.NotificationConsumer.as_asgi()),
]