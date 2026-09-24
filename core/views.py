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
    queryset = TypeVetement.objects.all()
    serializer_class = TypeVetementSerializer

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

        if not abonnement_actif and nb_modeles >= 5:
            raise PermissionDenied(
                "Limite atteinte : sans abonnement, vous ne pouvez créer que 5 modèles maximum."
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
        return Response({"is_maintenance": False})
    
    return Response({
        "is_maintenance": config.is_maintenance_mode,
        "message": config.maintenance_message
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

