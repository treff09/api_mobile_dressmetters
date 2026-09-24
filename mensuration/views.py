from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics,exceptions,permissions
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from core.models import MesureClient, LibelleMesure
from core.serializers import MesureClientSerializer, LibelleMesureSerializer

# ============================================================
# POINTS DU GABARIT (Pour Flutter : placement des points X, Y)
# ============================================================

class LibelleMesureListView(generics.ListCreateAPIView):
    serializer_class = LibelleMesureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Affiche les points système ET les points du client connecté."""
        return LibelleMesure.objects.filter(
            Q(client_profile__isnull=True) |
            Q(client_profile__user=self.request.user)
        )

    def perform_create(self, serializer):
        """Vérifie les doublons et associe au client."""
        nom = serializer.validated_data.get('nom')
        client_profile = self.request.user.client_profile

        # ✅ PROTECTION : Vérifier si ce nom existe déjà pour CE client
        if LibelleMesure.objects.filter(client_profile=client_profile, nom=nom).exists():
            raise exceptions.ValidationError({
                "error": f"Le point '{nom}' existe déjà dans vos mensurations."
            })

        serializer.save(client_profile=client_profile)

class LibelleMesureDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LibelleMesureSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Un client ne peut modifier/supprimer que SES propres points
        return LibelleMesure.objects.filter(client_profile__user=self.request.user)

    def perform_destroy(self, instance):
        # Sécurité supplémentaire : interdire la suppression si c'est un point système
        if instance.client_profile is None:
            raise exceptions.PermissionDenied("Impossible de supprimer un point système standard.")
        instance.delete()
# ============================================================
# MESURES DU CLIENT (Valeurs en cm)
# ============================================================

class ClientMesureView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mesures = MesureClient.objects.filter(client_profile__user=request.user)
        serializer = MesureClientSerializer(mesures, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data
        if not isinstance(data, list):
            return Response({"error": "Une liste de mesures est attendue"}, status=400)

        client_profile = request.user.client_profile
        results = []
        errors = []

        with transaction.atomic():
            for item in data:
                libelle_id = item.get('libelle_id')
                valeur = item.get('valeur', 0)

                # Vérifie que le LibelleMesure existe avant d'essayer de l'utiliser
                try:
                    libelle = LibelleMesure.objects.get(
                        pk=libelle_id,
                    )
                except LibelleMesure.DoesNotExist:
                    errors.append(f"Libellé #{libelle_id} introuvable, ignoré.")
                    continue  # on saute cet item au lieu de planter

                mesure, created = MesureClient.objects.update_or_create(
                    client_profile=client_profile,
                    libelle=libelle,
                    defaults={'valeur': valeur}
                )
                results.append(mesure)

        response_data = {"message": f"{len(results)} mesure(s) enregistrée(s)."}
        if errors:
            response_data["warnings"] = errors

        return Response(response_data, status=200)