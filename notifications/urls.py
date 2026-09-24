from django.urls import path
from .views import get_notifications, unread_notifications_count, mark_all_as_read

app_name = 'notifications' # Optionnel mais recommandé

urlpatterns = [
    # Route pour récupérer le nombre au démarrage de Flutter
    path('unread-count/', unread_notifications_count, name='unread_count'),
    
    # Route pour remettre à zéro quand on clique sur la cloche
    path('mark-read/', mark_all_as_read, name='mark_all_as_read'),
    path('', get_notifications, name='get_notifications'),
]