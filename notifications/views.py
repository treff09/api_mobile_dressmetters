from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication # Pour lire le token
from rest_framework.response import Response
from datetime import timedelta

from django.utils import timezone
from core.models import Notification

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def unread_notifications_count(request):
    """Renvoie le nombre de notifications non lues au démarrage de l'app"""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return Response({"unread_count": count})

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mark_all_as_read(request):
    """Appelé quand l'utilisateur clique sur la cloche"""
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"message": "Notifications marquées comme lues"})

# AJOUT DES DÉCORATEURS ICI (C'EST CE QUI MANQUAIT)
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_notifications(request):
    """Historique : toutes les notifications des 7 derniers jours, lues ou non.
    (Avant : seulement les non lues, donc elles disparaissaient dès qu'on ouvrait la cloche.)
    ?jours=N pour changer la durée (1 à 30)."""
    try:
        jours = max(1, min(30, int(request.GET.get('jours', 7))))
    except ValueError:
        jours = 7
    depuis = timezone.now() - timedelta(days=jours)
    notifications = (Notification.objects
                     .filter(user=request.user, created_at__gte=depuis)
                     .order_by('-created_at')[:200])

    data = []
    for n in notifications:
        local = timezone.localtime(n.created_at)
        data.append({
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "commande_id": n.commande_id,  # permet d'ouvrir la commande d'un appui
            "is_read": n.is_read,
            "created_at": local.isoformat(),
            "created_at_formatted": local.strftime("%H:%M"),  # gardé pour l'ancienne appli
        })

    return Response(data)
