import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import notifications.routing  # <--- Vérifie bien cet import

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dressmaker.settings') # <--- Remplace par ton nom de projet

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            notifications.routing.websocket_urlpatterns
        )
    ),
})