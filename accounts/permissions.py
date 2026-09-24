from rest_framework import permissions

class IsProfessionalOrReadOnly(permissions.BasePermission):
    """
    Permission personnalisée pour autoriser uniquement les utilisateurs professionnels
    à modifier ou supprimer des objets. Les lectures sont autorisées pour tous.
    """
    def has_permission(self, request, view):
        # Les requêtes GET, HEAD, OPTIONS (lectures) sont autorisées pour tout le monde
        if request.method in permissions.SAFE_METHODS:
            return True

        # Pour les autres méthodes (POST, PUT, PATCH, DELETE),
        # l'utilisateur doit être authentifié ET avoir un profil professionnel.
        return request.user.is_authenticated and hasattr(request.user, 'professional_profile')

    def has_object_permission(self, request, view, obj):
        # Pour les opérations sur un objet spécifique (ex: modifier un modèle),
        # on vérifie que l'utilisateur est le propriétaire (le professionnel qui a créé le modèle).
        # Si la permission has_permission a déjà vérifié que c'est un professionnel,
        # ici on vérifie s'il est le propriétaire de l'objet.
        if request.method in permissions.SAFE_METHODS:
            return True # Toujours autoriser la lecture s'il est déjà passé par has_permission

        # On vérifie si l'objet belongs au profil professionnel de l'utilisateur
        # Assurez-vous que 'obj' a une relation avec 'professional_profile'
        # Par exemple, si obj est un ModeleDisponible, et qu'il a une FK vers ProfessionalProfile
        # Vérifiez que obj.professional_profile est bien celui de l'utilisateur
        return request.user.is_authenticated and hasattr(request.user, 'professional_profile') and obj.professional_profile == request.user.professional_profile
    

# accounts/permissions.py
from rest_framework import permissions

class IsClientOrReadOnly(permissions.BasePermission):
    """
    Permission personnalisée pour autoriser uniquement les clients à créer des objets.
    Les lectures sont autorisées pour tous.
    """
    def has_permission(self, request, view):
        # Autorise les requêtes de lecture (GET, HEAD, OPTIONS) pour tout le monde
        if request.method in permissions.SAFE_METHODS:
            return True

        # Pour les requêtes de création/modification (POST, PUT, PATCH, DELETE),
        # l'utilisateur doit être authentifié ET avoir un profil client.
        return request.user.is_authenticated and hasattr(request.user, 'client_profile')

    def has_object_permission(self, request, view, obj):
        # Toujours autoriser la lecture sur un objet.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Vérifie si l'utilisateur est le propriétaire de l'objet.
        # Par exemple, si l'objet est une Mesure, on vérifie que
        # obj.client_profile est bien celui de l'utilisateur.
        return request.user.is_authenticated and hasattr(request.user, 'client_profile') and obj.client_profile == request.user.client_profile