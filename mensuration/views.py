from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics, exceptions, permissions
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from core.models import MesureClient, LibelleMesure, PositionGabaritClient
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

    def list(self, request, *args, **kwargs):
        """
        Surcharge pour injecter les positions personnalisées du client
        sur les points système avant de les retourner.
        """
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data

        # Charger toutes les positions perso du client en une seule requête
        try:
            client_profile = request.user.client_profile
            positions_perso = {
                pos.libelle_id: pos
                for pos in PositionGabaritClient.objects.filter(
                    client_profile=client_profile
                )
            }
        except Exception:
            positions_perso = {}

        # Remplacer position_x/position_y par les valeurs perso si elles existent
        libelles = list(queryset)
        for i, libelle in enumerate(libelles):
            if libelle.client_profile is None and libelle.id in positions_perso:
                pos = positions_perso[libelle.id]
                data[i]["position_x"] = pos.position_x
                data[i]["position_y"] = pos.position_y

        return Response(data)

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
        # Accès aux points du client ET aux points système
        return LibelleMesure.objects.filter(
            Q(client_profile__user=self.request.user) |
            Q(client_profile__isnull=True)
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()

        try:
            client_profile = request.user.client_profile
        except Exception:
            return Response(
                {"error": "Profil client introuvable."},
                status=status.HTTP_400_BAD_REQUEST
            )

        valeur    = request.data.get("valeur")
        position_x = request.data.get("position_x")
        position_y = request.data.get("position_y")

        if instance.client_profile is None:
            # ── Point SYSTÈME ──────────────────────────────────────
            # Sauvegarder la valeur dans MesureClient
            if valeur is not None:
                MesureClient.objects.update_or_create(
                    client_profile=client_profile,
                    libelle=instance,
                    defaults={"valeur": valeur}
                )

            # Sauvegarder la position personnalisée dans PositionGabaritClient
            if position_x is not None or position_y is not None:
                pos, _ = PositionGabaritClient.objects.get_or_create(
                    client_profile=client_profile,
                    libelle=instance,
                    defaults={
                        "position_x": instance.position_x,
                        "position_y": instance.position_y,
                    }
                )
                if position_x is not None:
                    pos.position_x = float(position_x)
                if position_y is not None:
                    pos.position_y = float(position_y)
                pos.save()

            # Retourner la position effective pour ce client
            try:
                pos = PositionGabaritClient.objects.get(
                    client_profile=client_profile, libelle=instance)
                px, py = pos.position_x, pos.position_y
            except PositionGabaritClient.DoesNotExist:
                px, py = instance.position_x, instance.position_y

            return Response({
                "id":         instance.id,
                "nom":        instance.nom,
                "position_x": px,
                "position_y": py,
                "categorie":  instance.categorie,
                "message":    "Position et mesure sauvegardées."
            }, status=status.HTTP_200_OK)

        # ── Point PERSONNALISÉ du client : mise à jour normale ──────
        return super().partial_update(request, *args, **kwargs)

    def perform_destroy(self, instance):
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