from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics, exceptions, permissions
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from core.models import (MesureClient, LibelleMesure, PositionGabaritClient, ModeleDisponible,
                         TypeVetement, PersonneMesuree)
from core.serializers import MesureClientSerializer, LibelleMesureSerializer


def resoudre_personne(request, personne_id=None):
    """
    Personne concernée (Moi, Junior…) pour le client connecté.
    Sans id -> « Moi ». Retourne None si l'id n'appartient pas au client.
    """
    client = getattr(request.user, 'client_profile', None)
    if client is None:
        return None
    if personne_id in (None, '', '0', 0, 'null'):
        return PersonneMesuree.moi(client)
    return client.personnes.filter(pk=personne_id).first()


def personne_json(p):
    return {"id": p.id, "prenom": "Moi" if p.est_moi else p.prenom, "genre": p.genre, "est_moi": p.est_moi,
            "nb_mesures": p.mesures.filter(valeur__gt=0).count()}

# ============================================================
# POINTS DU GABARIT (Pour Flutter : placement des points X, Y)
# ============================================================

class LibelleMesureListView(generics.ListCreateAPIView):
    serializer_class = LibelleMesureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Points affichés sur « Mes mensurations » :
        - les points système marqués « afficher par défaut »,
        - tout point (système ou couturier) pour lequel le client a déjà une valeur,
        - les points personnels du client.
        """
        user = self.request.user
        moi = resoudre_personne(self.request)
        deja_mesures = MesureClient.objects.filter(client_profile__user=user, personne=moi).values('libelle_id')
        return LibelleMesure.objects.filter(
            Q(client_profile__isnull=True, professional_profile__isnull=True, afficher_par_defaut=True) |
            Q(id__in=deja_mesures) |
            Q(client_profile__user=user)
        ).distinct().order_by('ordre', 'id')

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
                    personne=PersonneMesuree.moi(client_profile),
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
# MODE GUIDÉ : mesures à prendre pour un modèle donné
# GET /api/v1/mensuration/mesures-requises/?modele=<id>   (ou ?type=<id>)
# ============================================================
class MesuresRequisesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        client = getattr(request.user, 'client_profile', None)
        personne = resoudre_personne(request, request.query_params.get('personne'))
        if client and personne is None:
            return Response({"error": "Personne introuvable."}, status=404)
        genre = personne.genre if personne else (getattr(client, 'genre', None) or 'F')
        modele_id = request.query_params.get('modele')
        type_id = request.query_params.get('type')

        titre = ''
        if modele_id and modele_id != '0':
            modele = ModeleDisponible.objects.filter(pk=modele_id).select_related('type_vetement').first()
            if not modele:
                return Response({"error": "Modèle introuvable."}, status=404)
            mesures = list(modele.mesures_a_prendre())
            titre = modele.nom
        elif type_id:
            tv = TypeVetement.objects.filter(pk=type_id).first()
            if not tv:
                return Response({"error": "Type introuvable."}, status=404)
            mesures = list(tv.mesures_requises.all().order_by('ordre', 'id'))
            titre = tv.nom
        else:
            mesures = []

        # Aucune mesure définie (ex. sur-mesure) : on prend les mesures de base
        if not mesures:
            mesures = list(LibelleMesure.objects.filter(
                client_profile__isnull=True, professional_profile__isnull=True,
                afficher_par_defaut=True).order_by('ordre', 'id'))

        valeurs = {}
        positions_perso = {}
        if client:
            valeurs = {m.libelle_id: float(m.valeur) for m in
                       MesureClient.objects.filter(client_profile=client, personne=personne, libelle__in=mesures)}
            positions_perso = {p.libelle_id: p for p in
                               PositionGabaritClient.objects.filter(client_profile=client, libelle__in=mesures)}

        data = LibelleMesureSerializer(mesures, many=True, context={'request': request, 'genre': genre}).data
        for item in data:
            v = valeurs.get(item['id'])
            item['valeur'] = v if v and v > 0 else None
            p = positions_perso.get(item['id'])
            if p and item.get('type_mesure') == 'TOUR':
                item['position_x'], item['position_y'] = p.position_x, p.position_y
        homme = str(genre).strip().lower() in ('h', 'homme', 'm', 'masculin')
        return Response({"titre": titre, "genre": 'H' if homme else 'F', "mesures": data,
                         "personne": personne_json(personne) if personne else None})


# ============================================================
# PERSONNES SUIVIES PAR LE CLIENT (Moi, Junior, Malik…)
# GET  /api/v1/mensuration/personnes/            -> liste (« Moi » toujours en premier)
# POST /api/v1/mensuration/personnes/            -> {"prenom": "Junior", "genre": "H"|"F"}
# PATCH/DELETE /api/v1/mensuration/personnes/<id>/  (« Moi » ne peut pas être supprimé)
# ============================================================
class PersonnesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        client = getattr(request.user, 'client_profile', None)
        if not client:
            return Response([], status=200)
        PersonneMesuree.moi(client)
        return Response([personne_json(p) for p in client.personnes.all()])

    def post(self, request):
        client = getattr(request.user, 'client_profile', None)
        if not client:
            return Response({"error": "Réservé aux clients."}, status=403)
        prenom = (request.data.get('prenom') or '').strip()[:60]
        genre = 'H' if str(request.data.get('genre', '')).upper().startswith('H') else 'F'
        if not prenom:
            return Response({"error": "Écris le prénom."}, status=400)
        if prenom.lower() == 'moi' or client.personnes.filter(prenom__iexact=prenom).exists():
            return Response({"error": f"« {prenom} » existe déjà."}, status=400)
        p = PersonneMesuree.objects.create(client_profile=client, prenom=prenom, genre=genre)
        return Response(personne_json(p), status=201)


class PersonneDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        client = getattr(request.user, 'client_profile', None)
        return client.personnes.filter(pk=pk).first() if client else None

    def patch(self, request, pk):
        p = self._get(request, pk)
        if not p:
            return Response({"error": "Personne introuvable."}, status=404)
        if 'prenom' in request.data and not p.est_moi:
            prenom = (request.data.get('prenom') or '').strip()[:60]
            if prenom:
                p.prenom = prenom
        if 'genre' in request.data:
            p.genre = 'H' if str(request.data['genre']).upper().startswith('H') else 'F'
        p.save()
        return Response(personne_json(p))

    def delete(self, request, pk):
        p = self._get(request, pk)
        if not p:
            return Response({"error": "Personne introuvable."}, status=404)
        if p.est_moi:
            return Response({"error": "Tu ne peux pas supprimer « Moi »."}, status=400)
        p.delete()
        return Response(status=204)


# ============================================================
# BIBLIOTHÈQUE DE MESURES (couturier)
# GET  /api/v1/mensuration/bibliotheque/  -> mesures de l'app + les siennes
# POST /api/v1/mensuration/bibliotheque/  -> créer sa propre mesure
#      {"nom": "...", "type_mesure": "TOUR"|"LONGUEUR",
#       "position_x": .., "position_y": .., "fin_x": .., "fin_y": .., "aide": "..."}
#      (positions en % du gabarit homme ; reprises pour la femme)
# ============================================================
class BibliothequeMesuresView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pro = getattr(request.user, 'professional_profile', None)
        qs = LibelleMesure.objects.filter(client_profile__isnull=True, professional_profile__isnull=True)
        if pro:
            qs = LibelleMesure.objects.filter(
                Q(client_profile__isnull=True, professional_profile__isnull=True) |
                Q(professional_profile=pro)
            )
        qs = qs.order_by('ordre', 'id')
        return Response(LibelleMesureSerializer(qs, many=True, context={'request': request, 'genre': 'H'}).data)

    def post(self, request):
        pro = getattr(request.user, 'professional_profile', None)
        if not pro:
            return Response({"error": "Réservé aux couturiers."}, status=403)
        nom = (request.data.get('nom') or '').strip()
        if not nom:
            return Response({"error": "Donne un nom à la mesure."}, status=400)
        if LibelleMesure.objects.filter(professional_profile=pro, nom__iexact=nom).exists():
            return Response({"error": f"La mesure « {nom} » existe déjà."}, status=400)
        type_mesure = 'LONGUEUR' if request.data.get('type_mesure') == 'LONGUEUR' else 'TOUR'
        try:
            x = float(request.data.get('position_x', 50)); y = float(request.data.get('position_y', 50))
            fx = request.data.get('fin_x'); fy = request.data.get('fin_y')
            fx = float(fx) if fx not in (None, '') else None
            fy = float(fy) if fy not in (None, '') else None
        except (TypeError, ValueError):
            return Response({"error": "Position invalide."}, status=400)
        if type_mesure == 'LONGUEUR' and (fx is None or fy is None):
            return Response({"error": "Une longueur a besoin d'un point de départ et d'arrivée."}, status=400)
        lib = LibelleMesure.objects.create(
            professional_profile=pro, nom=nom, type_mesure=type_mesure,
            aide=(request.data.get('aide') or '')[:200],
            position_x=x, position_y=y,
            position_x_h=x, position_y_h=y, fin_x_h=fx, fin_y_h=fy,
            position_x_f=x, position_y_f=y, fin_x_f=fx, fin_y_f=fy,
            afficher_par_defaut=False, ordre=1000, categorie="Couturier",
        )
        return Response(LibelleMesureSerializer(lib, context={'request': request, 'genre': 'H'}).data, status=201)


# ============================================================
# MESURES DU CLIENT (Valeurs en cm)
# ============================================================

class ClientMesureView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ?personne=<id> (sans paramètre : « Moi »)
        personne = resoudre_personne(request, request.query_params.get('personne'))
        mesures = MesureClient.objects.filter(client_profile__user=request.user, personne=personne)
        serializer = MesureClientSerializer(mesures, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data
        if not isinstance(data, list):
            return Response({"error": "Une liste de mesures est attendue"}, status=400)

        client_profile = request.user.client_profile
        # ?personne=<id> (sans paramètre : « Moi »)
        personne = resoudre_personne(request, request.query_params.get('personne'))
        if personne is None:
            return Response({"error": "Personne introuvable."}, status=404)
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
                    personne=personne,
                    libelle=libelle,
                    defaults={'valeur': valeur}
                )
                results.append(mesure)

        response_data = {"message": f"{len(results)} mesure(s) enregistrée(s)."}
        if errors:
            response_data["warnings"] = errors

        return Response(response_data, status=200)