"""Signaler un contenu et bloquer un utilisateur (règle Apple 1.2 — contenus des utilisateurs)."""
from django.contrib.auth import get_user_model
from django.core.mail import mail_admins
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AvisCouturier, Blocage, ModeleDisponible, Signalement

# Un avis signalé par 3 personnes différentes est masqué tout de suite, en attendant l'examen.
SEUIL_MASQUAGE = 3


def _proprietaire(type_, objet_id):
    """Utilisateur qui a publié le contenu signalé (ou None)."""
    if type_ == 'avis':
        a = AvisCouturier.objects.select_related('client_profile__user').filter(id=objet_id).first()
        return a.client_profile.user if a else None
    if type_ == 'modele':
        m = ModeleDisponible.objects.select_related('professional_profile__user').filter(id=objet_id).first()
        return m.professional_profile.user if m and m.professional_profile else None
    if type_ == 'utilisateur':
        return get_user_model().objects.filter(id=objet_id).first()
    return None


class SignalerView(APIView):
    """POST {type: avis|modele|utilisateur, objet_id, motif, details, bloquer: bool}"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        type_ = request.data.get('type')
        motif = request.data.get('motif') or 'autre'
        try:
            objet_id = int(request.data.get('objet_id'))
        except (TypeError, ValueError):
            return Response({"detail": "objet_id manquant."}, status=status.HTTP_400_BAD_REQUEST)
        if type_ not in dict(Signalement.TYPES) or motif not in dict(Signalement.MOTIFS):
            return Response({"detail": "Type ou motif invalide."}, status=status.HTTP_400_BAD_REQUEST)
        proprio = _proprietaire(type_, objet_id)
        if proprio is None:
            return Response({"detail": "Contenu introuvable."}, status=status.HTTP_404_NOT_FOUND)

        s, cree = Signalement.objects.get_or_create(
            auteur=request.user, type=type_, objet_id=objet_id,
            defaults={'motif': motif, 'details': (request.data.get('details') or '')[:1000]})

        if type_ == 'avis' and Signalement.objects.filter(type='avis', objet_id=objet_id).values('auteur').distinct().count() >= SEUIL_MASQUAGE:
            AvisCouturier.objects.filter(id=objet_id).update(visible=False)

        if request.data.get('bloquer') and proprio != request.user:
            Blocage.objects.get_or_create(auteur=request.user, bloque=proprio)

        if cree:
            try:
                mail_admins(f"[Dress'Matter] Signalement : {s}",
                            f"Par {request.user.email} — détails : {s.details or '-'}\n"
                            "À examiner sous 24 h dans l'admin (Core › Signalements).", fail_silently=True)
            except Exception:
                pass
        return Response({"detail": "Merci, le signalement a été envoyé. Nous l'examinons sous 24 h."},
                        status=status.HTTP_201_CREATED)


class BloquerView(APIView):
    """GET : liste des personnes bloquées. POST {user_id} : bloquer. DELETE {user_id} : débloquer."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = []
        for b in Blocage.objects.filter(auteur=request.user).select_related('bloque'):
            u = b.bloque
            pro = getattr(u, 'professional_profile', None)
            cli = getattr(u, 'client_profile', None)
            nom = (getattr(pro, 'nom_entreprise', '') or getattr(cli, 'prenom', '') or u.first_name or 'Utilisateur')
            data.append({"user_id": u.id, "nom": nom, "date": b.date})
        return Response(data)

    def _cible(self, request):
        try:
            return get_user_model().objects.get(id=int(request.data.get('user_id')))
        except (TypeError, ValueError, get_user_model().DoesNotExist):
            return None

    def post(self, request):
        u = self._cible(request)
        if u is None or u == request.user:
            return Response({"detail": "Utilisateur introuvable."}, status=status.HTTP_400_BAD_REQUEST)
        Blocage.objects.get_or_create(auteur=request.user, bloque=u)
        return Response({"detail": "Utilisateur bloqué."}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        u = self._cible(request)
        if u is not None:
            Blocage.objects.filter(auteur=request.user, bloque=u).delete()
        return Response({"detail": "Utilisateur débloqué."})
