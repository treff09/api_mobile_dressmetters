# core/views.py
from rest_framework import viewsets, permissions, status, generics, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
from django.views.generic import TemplateView
from accounts.permissions import IsProfessionalOrReadOnly 
from .models import (
    ConditionGenerale, OffreAbonnement, TypeVetement, Abonnement,
    ModeleDisponible, Commande, ModeleCommande,
    LibelleMesure, MesureClient, AppConfiguration,
)
from .serializers import (
    OffreAbonnementSerializer, TypeVetementSerializer, 
    AbonnementSerializer, ModeleDisponibleSerializer, 
    CommandeSerializer, ModeleCommandeSerializer,
    LibelleMesureSerializer, MesureClientSerializer,
)

# ============================================================
# PARTIE : MESURES (MISE À JOUR DYNAMIQUE)
# ============================================================

class LibelleMesureViewSet(viewsets.ModelViewSet):
    """Permet aux pros de gérer leurs types de mesures (points sur gabarit)"""
    queryset = LibelleMesure.objects.all()
    serializer_class = LibelleMesureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # On affiche les libellés créés par l'admin (ceux sans pro_profile)
        # OU ceux créés spécifiquement par ce pro
        from django.db.models import Q
        if hasattr(self.request.user, 'professional_profile'):
            return LibelleMesure.objects.filter(
                Q(professional_profile=self.request.user.professional_profile) | 
                Q(professional_profile__isnull=True)
            )
        return LibelleMesure.objects.filter(professional_profile__isnull=True)

class MesureClientViewSet(viewsets.ModelViewSet):
    """Gère les valeurs des mesures pour les clients"""
    queryset = MesureClient.objects.all()
    serializer_class = MesureClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if hasattr(self.request.user, 'client_profile'):
            return MesureClient.objects.filter(client_profile=self.request.user.client_profile)
        return MesureClient.objects.none()

# ============================================================
# PARTIE : CATALOGUE & ABONNEMENTS
# ============================================================

class TypeVetementViewSet(viewsets.ModelViewSet):
    """
    Types de vêtements : ceux de l'application + ceux créés par le couturier connecté.
    Un couturier peut créer ses propres types (POST) et choisir leurs mesures.
    """
    queryset = TypeVetement.objects.all()
    serializer_class = TypeVetementSerializer

    def get_queryset(self):
        from django.db.models import Q
        user = self.request.user
        qs = TypeVetement.objects.filter(professional_profile__isnull=True)
        if user.is_authenticated and hasattr(user, 'professional_profile'):
            qs = TypeVetement.objects.filter(
                Q(professional_profile__isnull=True) | Q(professional_profile=user.professional_profile)
            )
        return qs.order_by('nom')

    def perform_create(self, serializer):
        from rest_framework.exceptions import PermissionDenied, ValidationError
        user = self.request.user
        if not (user.is_authenticated and hasattr(user, 'professional_profile')):
            raise PermissionDenied("Seul un couturier peut créer un type de vêtement.")
        pro = user.professional_profile
        nom = serializer.validated_data.get('nom', '').strip()
        if TypeVetement.objects.filter(nom__iexact=nom, professional_profile__isnull=True).exists() or \
           TypeVetement.objects.filter(nom__iexact=nom, professional_profile=pro).exists():
            raise ValidationError({"error": f"Le type « {nom} » existe déjà."})
        serializer.save(professional_profile=pro, nom=nom)

    def perform_update(self, serializer):
        from rest_framework.exceptions import PermissionDenied
        pro = getattr(self.request.user, 'professional_profile', None)
        if serializer.instance.professional_profile_id is None or serializer.instance.professional_profile != pro:
            raise PermissionDenied("Vous ne pouvez modifier que vos propres types.")
        serializer.save()

    def perform_destroy(self, instance):
        from rest_framework.exceptions import PermissionDenied
        pro = getattr(self.request.user, 'professional_profile', None)
        if instance.professional_profile_id is None or instance.professional_profile != pro:
            raise PermissionDenied("Vous ne pouvez supprimer que vos propres types.")
        instance.delete()

class AbonnementViewSet(viewsets.ModelViewSet):
    queryset = Abonnement.objects.all()
    serializer_class = AbonnementSerializer

class ModeleListAPIView(APIView):
    permission_classes = [IsAuthenticated, IsProfessionalOrReadOnly]

    def get(self, request, *args, **kwargs):
        user = request.user
        now = timezone.now()

        if hasattr(user, 'professional_profile'):
            pro_profile = user.professional_profile
            abonnement_actif = Abonnement.objects.filter(
                professional_profile=pro_profile,
                date_fin__gt=now
            ).exists()

            queryset = ModeleDisponible.objects.filter(
                professional_profile=pro_profile
            ).order_by('-id')

            if not abonnement_actif:
                queryset = queryset[:5]

            serializer = ModeleDisponibleSerializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(
            {'detail': 'Accès réservé aux professionnels.'},
            status=status.HTTP_403_FORBIDDEN
        )

class ModeleCreateAPIView(generics.CreateAPIView):
    queryset = ModeleDisponible.objects.all()
    serializer_class = ModeleDisponibleSerializer
    permission_classes = [IsAuthenticated, IsProfessionalOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]

    def perform_create(self, serializer):
        user = self.request.user
        pro_profile = user.professional_profile
        now = timezone.now()

        nb_modeles = ModeleDisponible.objects.filter(
            professional_profile=pro_profile
        ).count()

        abonnement_actif = Abonnement.objects.filter(
            professional_profile=pro_profile,
            date_fin__gt=now
        ).exists()

        limite = AppConfiguration.limite_modeles_gratuits()  # réglable dans l'admin
        if not abonnement_actif and nb_modeles >= limite:
            raise PermissionDenied(
                f"Limite atteinte : sans abonnement, vous ne pouvez créer que {limite} modèles maximum."
            )

        serializer.save(professional_profile=pro_profile)

class ModeleDetailAPIView(generics.RetrieveAPIView):
    queryset = ModeleDisponible.objects.all()
    serializer_class = ModeleDisponibleSerializer
    permission_classes = [IsAuthenticated, IsProfessionalOrReadOnly]
    lookup_field = 'id'

class ModeleUpdateAPIView(generics.UpdateAPIView):
    queryset = ModeleDisponible.objects.all()
    serializer_class = ModeleDisponibleSerializer
    permission_classes = [IsAuthenticated, IsProfessionalOrReadOnly]
    lookup_field = 'id'

    def perform_update(self, serializer):
        serializer.save(professional_profile=self.request.user.professional_profile)

class ModeleDestroyAPIView(generics.DestroyAPIView):
    queryset = ModeleDisponible.objects.all()
    permission_classes = [IsAuthenticated, IsProfessionalOrReadOnly]
    lookup_field = 'id'

    def get_queryset(self):
        if hasattr(self.request.user, 'professional_profile'):
            return ModeleDisponible.objects.filter(professional_profile=self.request.user.professional_profile)
        return ModeleDisponible.objects.none()

# ============================================================
# PARTIE : COMMANDES
# ============================================================

class CommandeViewSet(viewsets.ModelViewSet):
    queryset = Commande.objects.all()
    serializer_class = CommandeSerializer

class ModeleCommandeViewSet(viewsets.ModelViewSet):
    queryset = ModeleCommande.objects.all()
    serializer_class = ModeleCommandeSerializer

class TypeVetementListAPIView(generics.ListAPIView):
    queryset = TypeVetement.objects.all()
    serializer_class = TypeVetementSerializer

class OffreAbonnementListView(generics.ListAPIView):
    queryset = OffreAbonnement.objects.all().order_by('prix')
    serializer_class = OffreAbonnementSerializer
    permission_classes = [IsAuthenticated]

# ============================================================
# PARTIE : UTILITAIRES & STATUS
# ============================================================

class UserProfileTypeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if hasattr(user, 'professional_profile'):
            return Response({'type_de_compte': 'professionnel'}, status=status.HTTP_200_OK)
        if hasattr(user, 'client_profile'):
            return Response({'type_de_compte': 'client', 'genre': user.client_profile.genre}, status=status.HTTP_200_OK)
        return Response({'type_de_compte': 'inconnu'}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([AllowAny])
def check_app_status(request):
    config = AppConfiguration.objects.first()
    if not config:
        return Response({"is_maintenance": False, "nb_modeles_gratuits": 5})
    
    return Response({
        "is_maintenance": config.is_maintenance_mode,
        "message": config.maintenance_message,
        "nb_modeles_gratuits": config.nb_modeles_gratuits,
    })



from django.shortcuts import render
from .models import PrivacyPolicy

def privacy_policy_view(request):
    # On récupère la dernière version enregistrée
    policy = PrivacyPolicy.objects.order_by('-derniere_mise_a_jour').last()
    return render(request, 'privacy.html', {'policy': policy})

def cgu_view(request):
    cgu = ConditionGenerale.objects.last()
    return render(request, 'cgu.html', {'cgu': cgu})

