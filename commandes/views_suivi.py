"""
Suivi des commandes : étapes de fabrication, paiements reçus, relances, essayage,
avis des clients, tableau de bord du couturier, appareils (notifications push), parrainage.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (AppareilPush, AvisCouturier, Commande, PaiementCommande,
                         ProfessionalProfile, note_moyenne)
from core.push import notifier

ETAPES = dict(Commande.ETAPES)
ORDRE_ETAPES = [e for e, _ in Commande.ETAPES]
MESSAGES_ETAPE = {
    'COUPE': "Ton couturier a commencé la coupe de ton tissu ✂️",
    'COUTURE': "Ta tenue est en cours de couture 🧵",
    'ESSAYAGE': "Ta tenue est prête pour l'essayage 👗",
    'PRETE': "Ta tenue est prête ! Tu peux passer la récupérer 🎉",
    'LIVREE': "Ta commande est livrée. Merci ! Laisse un avis à ton couturier ⭐",
}


def _f(montant):
    return f"{int(montant):,} F".replace(',', ' ')


def _commande_du_pro(request, pk):
    c = get_object_or_404(Commande.objects.select_related('client_profile__user', 'professional_profile__user'), pk=pk)
    if c.professional_profile.user_id != request.user.id:
        return None
    return c


def _recalculer_paiement(c):
    total_recu = c.paiements.aggregate(s=Sum('montant'))['s'] or Decimal('0')
    c.montant_paye = total_recu
    total = c.total_commande or Decimal('0')
    c.reste_a_payer = max(total - total_recu, Decimal('0'))
    if total > 0 and total_recu >= total:
        c.statut_paiement = 'TOTALEMENT_PAYE'
    elif total_recu > 0:
        c.statut_paiement = 'ACOMPTE_PAYE'
    else:
        c.statut_paiement = 'EN_ATTENTE'


def suivi_json(c):
    """Bloc « suivi » ajouté au détail d'une commande."""
    return {
        "etape": c.etape,
        "etape_libelle": ETAPES.get(c.etape, c.etape),
        "etapes": [{"code": e, "libelle": l} for e, l in Commande.ETAPES],
        "etape_maj_le": c.etape_maj_le,
        "date_essayage": c.date_essayage,
        "paiements": [{"id": p.id, "montant": p.montant, "moyen": p.moyen, "note": p.note, "date": p.date}
                      for p in c.paiements.all()],
    }


class EtapeCommandeView(APIView):
    """PATCH {etape: 'COUTURE'} — le couturier avance la fabrication, le client est prévenu."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        c = _commande_du_pro(request, pk)
        if c is None:
            return Response({"error": "Réservé au couturier de la commande."}, status=403)
        etape = (request.data.get('etape') or '').upper()
        if etape not in ETAPES:
            return Response({"error": "Étape inconnue."}, status=400)
        if etape == 'LIVREE':
            return Response({"error": "Utilise « C'est livré » pour terminer la commande."}, status=400)
        c.etape = etape
        c.etape_maj_le = timezone.now()
        if etape != 'RECUE' and (c.statut or '').lower().startswith('en attente'):
            c.statut = 'En cours'
        c.save(update_fields=['etape', 'etape_maj_le', 'statut'])
        if etape in MESSAGES_ETAPE:
            notifier(c.client_profile.user, ETAPES[etape], f"Commande #{c.id} : {MESSAGES_ETAPE[etape]}", c.id, 'ETAPE')
        return Response(suivi_json(c))


class EssayageCommandeView(APIView):
    """PATCH {date_essayage: ISO 8601 | null} — rendez-vous d'essayage (rappel la veille)."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        c = _commande_du_pro(request, pk)
        if c is None:
            return Response({"error": "Réservé au couturier de la commande."}, status=403)
        brut = request.data.get('date_essayage')
        d = parse_datetime(brut) if brut else None
        if brut and d is None:
            return Response({"error": "Date invalide."}, status=400)
        if d is not None and timezone.is_naive(d):
            d = timezone.make_aware(d)
        ancienne = c.date_essayage
        if ancienne == d:
            return Response(suivi_json(c))  # rien n'a changé : pas de notification
        c.date_essayage = d
        c.save(update_fields=['date_essayage'])
        atelier = c.professional_profile.nom_entreprise
        fmt = lambda x: f"{timezone.localtime(x):%d/%m} à {timezone.localtime(x):%Hh%M}"
        if d and not ancienne:
            notifier(c.client_profile.user, "Rendez-vous d'essayage",
                     f"Essayage de ta commande #{c.id} le {fmt(d)} chez {atelier}.", c.id, 'ESSAYAGE')
        elif d and ancienne:
            notifier(c.client_profile.user, "Essayage déplacé",
                     f"Ton essayage (commande #{c.id}) est déplacé : nouveau rendez-vous le {fmt(d)} "
                     f"(au lieu du {fmt(ancienne)}) chez {atelier}.", c.id, 'ESSAYAGE')
        else:
            notifier(c.client_profile.user, "Essayage annulé",
                     f"Ton rendez-vous d'essayage du {fmt(ancienne)} (commande #{c.id}) est annulé. "
                     f"{atelier} te recontactera.", c.id, 'ESSAYAGE')
        return Response(suivi_json(c))


class PaiementsCommandeView(APIView):
    """GET : paiements reçus. POST {montant, moyen, note} : le couturier enregistre de l'argent reçu."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        c = get_object_or_404(Commande, pk=pk)
        if request.user.id not in (c.professional_profile.user_id, c.client_profile.user_id):
            return Response(status=403)
        return Response(suivi_json(c))

    def post(self, request, pk):
        c = _commande_du_pro(request, pk)
        if c is None:
            return Response({"error": "Réservé au couturier de la commande."}, status=403)
        try:
            montant = Decimal(str(request.data.get('montant', '')).replace(' ', ''))
        except InvalidOperation:
            return Response({"error": "Montant invalide."}, status=400)
        if montant <= 0:
            return Response({"error": "Le montant doit être positif."}, status=400)
        moyen = request.data.get('moyen') or 'ESPECE'
        if moyen not in dict(Commande.MOYEN_PAIEMENT_CHOICES):
            moyen = 'ESPECE'
        with transaction.atomic():
            PaiementCommande.objects.create(commande=c, montant=montant, moyen=moyen,
                                            note=(request.data.get('note') or '')[:200])
            _recalculer_paiement(c)
            c.save(update_fields=['montant_paye', 'reste_a_payer', 'statut_paiement'])
        msg = f"Paiement de {_f(montant)} reçu pour ta commande #{c.id}."
        msg += f" Reste à payer : {_f(c.reste_a_payer)}." if c.reste_a_payer > 0 else " Tout est payé, merci !"
        notifier(c.client_profile.user, "Paiement reçu", msg, c.id, 'PAIEMENT')
        return Response(suivi_json(c), status=201)


class SupprimerPaiementView(APIView):
    """DELETE : corriger une erreur de saisie."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, paiement_id):
        c = _commande_du_pro(request, pk)
        if c is None:
            return Response(status=403)
        get_object_or_404(PaiementCommande, id=paiement_id, commande=c).delete()
        _recalculer_paiement(c)
        c.save(update_fields=['montant_paye', 'reste_a_payer', 'statut_paiement'])
        return Response(suivi_json(c))


class RelancerPaiementView(APIView):
    """POST — rappel au client du reste à payer (une fois par jour maximum)."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from core.models import Notification
        c = _commande_du_pro(request, pk)
        if c is None:
            return Response(status=403)
        if not c.reste_a_payer or c.reste_a_payer <= 0:
            return Response({"error": "Cette commande est déjà payée."}, status=400)
        if Notification.objects.filter(user=c.client_profile.user, title="Rappel de paiement", commande_id=c.id,
                                       created_at__gte=timezone.now() - timedelta(hours=20)).exists():
            return Response({"error": "Le client a déjà été relancé aujourd'hui."}, status=429)
        notifier(c.client_profile.user, "Rappel de paiement",
                 f"Il reste {_f(c.reste_a_payer)} à payer pour ta commande #{c.id} chez {c.professional_profile.nom_entreprise}.",
                 c.id, 'PAIEMENT')
        return Response({"message": "Client relancé."})


# ── AVIS ─────────────────────────────────────────────────────

class AvisCommandeView(APIView):
    """POST {note: 1-5, commentaire} — le client note son couturier après la livraison."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        c = get_object_or_404(Commande.objects.select_related('client_profile', 'professional_profile__user'), pk=pk)
        if c.client_profile.user_id != request.user.id:
            return Response({"error": "Seul le client de la commande peut donner son avis."}, status=403)
        if not ((c.statut or '').lower().startswith('termin') or c.etape == 'LIVREE'):
            return Response({"error": "Tu pourras donner ton avis après la livraison."}, status=400)
        try:
            note = int(request.data.get('note'))
        except (TypeError, ValueError):
            note = 0
        if not 1 <= note <= 5:
            return Response({"error": "Choisis une note de 1 à 5 étoiles."}, status=400)
        avis, cree = AvisCouturier.objects.update_or_create(
            commande=c, defaults={"professional_profile": c.professional_profile, "client_profile": c.client_profile,
                                  "note": note, "commentaire": (request.data.get('commentaire') or '')[:1000]})
        if cree:
            notifier(c.professional_profile.user, "Nouvel avis",
                     f"{c.client_profile.prenom or 'Un client'} t'a donné {note}★ pour la commande #{c.id}.", c.id, 'AVIS')
        return Response({"note": avis.note, "commentaire": avis.commentaire}, status=201 if cree else 200)


class AvisCouturierListView(APIView):
    """GET — note moyenne et derniers avis d'un couturier."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pro_id):
        pro = get_object_or_404(ProfessionalProfile, id=pro_id)
        moyenne, nombre = note_moyenne(pro)
        avis = AvisCouturier.objects.filter(professional_profile=pro, visible=True).select_related('client_profile')[:30]
        return Response({
            "moyenne": moyenne, "nombre": nombre,
            "avis": [{"note": a.note, "commentaire": a.commentaire, "date": a.date,
                      "client": (a.client_profile.prenom or 'Client').strip()} for a in avis],
        })


# ── TABLEAU DE BORD DU COUTURIER ─────────────────────────────

class TableauDeBordView(APIView):
    """GET — chiffres du mois : commandes, argent reçu, reste à encaisser, meilleurs modèles."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pro = getattr(request.user, 'professional_profile', None)
        if pro is None:
            return Response(status=403)
        debut = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cmds = Commande.objects.filter(professional_profile=pro)
        du_mois = cmds.filter(date_creation__gte=debut)
        recu_mois = PaiementCommande.objects.filter(commande__professional_profile=pro, date__gte=debut) \
            .aggregate(s=Sum('montant'))['s'] or 0
        a_encaisser = cmds.exclude(statut__icontains='termin').aggregate(s=Sum('reste_a_payer'))['s'] or 0
        top = (du_mois.filter(articles__modele_disponible__isnull=False)
               .values('articles__modele_disponible__nom').annotate(n=Count('id')).order_by('-n')[:3])
        moyenne, nombre = note_moyenne(pro)
        return Response({
            "commandes_mois": du_mois.count(),
            "en_cours": cmds.exclude(statut__icontains='termin').count(),
            "livrees_mois": du_mois.filter(statut__icontains='termin').count(),
            "recu_mois": recu_mois,
            "a_encaisser": a_encaisser,
            "meilleurs_modeles": [{"nom": t['articles__modele_disponible__nom'], "commandes": t['n']} for t in top],
            "note_moyenne": moyenne, "nombre_avis": nombre,
        })


# ── APPAREILS (notifications sur le téléphone) ───────────────

class AppareilPushView(APIView):
    """POST {token, plateforme} : enregistre le téléphone. DELETE {token} : à la déconnexion."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = (request.data.get('token') or '').strip()
        if not token:
            return Response({"error": "token requis"}, status=400)
        AppareilPush.objects.update_or_create(token=token, defaults={
            "user": request.user, "plateforme": (request.data.get('plateforme') or 'android')[:10]})
        return Response({"ok": True})

    def delete(self, request):
        AppareilPush.objects.filter(user=request.user, token=(request.data.get('token') or '').strip()).delete()
        return Response({"ok": True})


# ── PARRAINAGE ───────────────────────────────────────────────

def code_parrainage(pro):
    if not pro.code_parrainage:
        import secrets
        base = ''.join(ch for ch in (pro.nom_entreprise or pro.nom or 'DM').upper() if ch.isalnum())[:4] or 'DM'
        while True:
            code = f"{base}{secrets.randbelow(9000) + 1000}"
            if not ProfessionalProfile.objects.filter(code_parrainage=code).exists():
                break
        pro.code_parrainage = code
        pro.save(update_fields=['code_parrainage'])
    return pro.code_parrainage


class ParrainageView(APIView):
    """GET — mon code, nombre de couturiers invités, mois gagnés."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pro = getattr(request.user, 'professional_profile', None)
        if pro is None:
            return Response(status=403)
        code = code_parrainage(pro)
        filleuls = pro.filleuls.all()
        return Response({
            "code": code,
            "invites": filleuls.count(),
            "mois_gagnes": filleuls.filter(parrainage_recompense=True).count(),
            "message": (f"Rejoins-moi sur Dress'Matter, l'appli des couturiers ! "
                        f"À l'inscription, entre mon code {code}. "
                        f"https://play.google.com/store/apps/details?id=com.trefftechnologies.dressmatter"),
        })


def recompenser_parrain(filleul):
    """
    Appelé APRÈS un premier abonnement payé par le filleul : le parrain gagne 30 jours de Premium.
    N'affecte jamais le paiement du filleul (simple bonus ajouté ensuite).
    """
    from core.models import Abonnement
    if not filleul.parrain_id or filleul.parrainage_recompense:
        return False
    with transaction.atomic():
        f = ProfessionalProfile.objects.select_for_update().get(id=filleul.id)
        if f.parrainage_recompense:
            return False
        now = timezone.now()
        abo, _ = Abonnement.objects.select_for_update().get_or_create(
            professional_profile_id=f.parrain_id, defaults={"date_fin": now})
        depart = abo.date_fin if (abo.date_fin and abo.date_fin > now) else now
        abo.date_fin = depart + timedelta(days=30)
        abo.save(update_fields=['date_fin'])
        f.parrainage_recompense = True
        f.save(update_fields=['parrainage_recompense'])
    notifier(f.parrain.user, "1 mois Premium offert 🎁",
             f"{f.nom_entreprise} s'est abonné grâce à ton code : tu gagnes 30 jours de Premium !")
    return True
