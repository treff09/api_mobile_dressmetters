from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication # Pour lire le token
from rest_framework.response import Response
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
    """Récupère la liste des 20 dernières notifications"""
    # Ici, request.user sera maintenant bien reconnu grâce au token
    notifications = Notification.objects.filter(user=request.user ,is_read=False).order_by('-created_at')[:20]
    
    data = []
    for n in notifications:
        data.append({
            "title": n.title,
            "message": n.message,
            "created_at_formatted": n.created_at.strftime("%H:%M") 
        })
        
    return Response(data)