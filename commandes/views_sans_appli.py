"""
Commandes de clients SANS l'application.

1. Le couturier enregistre la commande depuis son interface (nom, numéro,
   vêtement, mesures prises à l'atelier).
2. Il envoie au client, par WhatsApp, un lien de suivi : /s/<jeton>/
3. Le client suit l'avancement sur cette page web, sans rien installer.
4. S'il s'inscrit dans l'application, il ouvre son lien (ou le colle dans
   « Récupérer mes commandes ») : ses commandes et ses mesures, liées à son
   numéro, rejoignent son compte.

Sécurité : le numéro de téléphone n'est pas vérifié à l'inscription. On ne
rattache donc JAMAIS sur le numéro seul : il faut le jeton du lien, reçu sur le
WhatsApp du client. Une fois ce lien prouvé, tout ce qui a été enregistré par
des couturiers avec le même numéro est rattaché.

Aucun paiement n'est fait ici : les paiements de la commande restent hors appli
(espèces / Mobile Money), et le Premium reste payé sur le site web.
"""
import json
import os
import re
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import render
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.cache import never_cache
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (ClientProfile, Commande, LibelleMesure, MesureClient, ModeleCommande,
                         ModeleDisponible, PersonneMesuree, ValeurMesureCommande, quota_commandes)

User = get_user_model()

PACKAGE_ANDROID = "com.trefftechnologies.dressmatter"
LIEN_PLAY_STORE = f"https://play.google.com/store/apps/details?id={PACKAGE_ANDROID}"


# ------------------------------------------------------------------ outils
def cle_telephone(numero):
    """Numéro comparable : chiffres seulement, 10 derniers (avec ou sans indicatif)."""
    chiffres = re.sub(r"\D", "", str(numero or ""))
    return chiffres[-10:] if len(chiffres) >= 8 else ""


def _base_site(request):
    base = os.getenv("SITE_URL", "").strip().rstrip("/")
    return base or request.build_absolute_uri("/").rstrip("/")


def url_suivi(request, commande):
    return f"{_base_site(request)}/s/{commande.jeton_suivi()}/"


def _nom_atelier(pro):
    return pro.nom_entreprise or f"{pro.prenom} {pro.nom}".strip() or "Votre couturier"


def message_whatsapp(request, commande):
    cp = commande.client_profile
    prenom = (cp.prenom or "").strip()
    return (f"Bonjour{(' ' + prenom) if prenom else ''} 👋\n"
            f"{_nom_atelier(commande.professional_profile)} a bien enregistré votre commande.\n"
            f"Suivez son avancement ici : {url_suivi(request, commande)}\n"
            f"Avec l'application Dress'Matter, retrouvez aussi vos mesures et toutes vos commandes.")


def lien_whatsapp(request, commande):
    chiffres = re.sub(r"\D", "", commande.client_profile.numero_telephone or "")
    return f"https://wa.me/{chiffres}?text={quote(message_whatsapp(request, commande))}"


def _pro(request):
    return getattr(request.user, 'professional_profile', None)


def _decimal(v, defaut=None):
    if v in (None, "", "null"):
        return defaut
    try:
        return Decimal(str(v).replace(",", ".").replace(" ", ""))
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------- 1. clients déjà enregistrés
class ClientsSansAppliView(APIView):
    """GET : clients sans l'appli déjà servis par ce couturier (pour une 2e commande)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pro = _pro(request)
        if pro is None:
            return Response({"error": "Réservé aux couturiers."}, status=403)
        q = (request.query_params.get('q') or '').strip()
        clients = ClientProfile.objects.filter(invite=True, commandes__professional_profile=pro).distinct()
        if q:
            clients = clients.filter(nom__icontains=q) | clients.filter(prenom__icontains=q) | \
                clients.filter(numero_telephone__icontains=q)
        resultat = []
        for cp in clients.order_by('-id')[:50]:
            moi = cp.personnes.filter(est_moi=True).first()
            mesures = MesureClient.objects.filter(client_profile=cp, personne=moi).select_related('libelle') if moi else []
            resultat.append({
                "id": cp.id, "nom": cp.nom, "prenom": cp.prenom,
                "telephone": cp.numero_telephone, "genre": cp.genre,
                "mesures": [{"libelle": m.libelle_id, "nom": m.libelle.nom, "valeur": m.valeur} for m in mesures],
            })
        return Response(resultat)


# ------------------------------------------------ 2. créer la commande
class CommandeSansAppliView(APIView):
    """
    POST (couturier) — champs :
      prenom, nom, telephone (obligatoire), genre (H/F)
      modele_disponible (id, facultatif) ou description (texte)
      total, acompte (facultatifs ; par défaut ceux du modèle)
      date_livraison (AAAA-MM-JJ), image_personnalisee (photo, facultative)
      mesures : liste [{libelle: id} ou {nom: "Tour de taille"}, valeur: 80]
                (en multipart : chaîne JSON)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        pro = _pro(request)
        if pro is None:
            return Response({"error": "Réservé aux couturiers."}, status=403)
        d = request.data

        # Numéro gardé sans espaces : « +225 07 11… » et « 0711… » se retrouvent
        telephone = re.sub(r"[^\d+]", "", str(d.get('telephone') or ''))[:20]
        cle = cle_telephone(telephone)
        if not cle:
            return Response({"error": "Numéro de téléphone du client invalide."}, status=400)
        prenom = (d.get('prenom') or '').strip()[:100]
        nom = (d.get('nom') or '').strip()[:100]
        if not (prenom or nom):
            return Response({"error": "Indiquez au moins le prénom du client."}, status=400)

        modele = None
        if d.get('modele_disponible') not in (None, '', '0', 'null'):
            modele = ModeleDisponible.objects.filter(pk=d.get('modele_disponible'), professional_profile=pro).first()
            if modele is None:
                return Response({"error": "Modèle introuvable."}, status=400)
        description = (d.get('description') or '').strip()[:255]
        if modele is None and not description:
            return Response({"error": "Choisissez un modèle ou décrivez le vêtement."}, status=400)

        total = _decimal(d.get('total'), Decimal(str(modele.price)) if modele else Decimal('0'))
        acompte = _decimal(d.get('acompte'), Decimal(str(modele.acompte or 0)) if modele else Decimal('0'))
        if total is None or acompte is None or total < 0 or acompte < 0:
            return Response({"error": "Montant invalide."}, status=400)

        date_livraison = None
        if d.get('date_livraison'):
            date_livraison = parse_datetime(str(d.get('date_livraison')))
            if date_livraison is None:
                jour = parse_date(str(d.get('date_livraison')))
                if jour:
                    from datetime import datetime, time
                    from django.utils import timezone
                    date_livraison = timezone.make_aware(datetime.combine(jour, time(12, 0)))

        mesures = d.get('mesures') or []
        if isinstance(mesures, str):
            try:
                mesures = json.loads(mesures)
            except ValueError:
                return Response({"error": "Mesures illisibles."}, status=400)

        # Même règle que les commandes passées par les clients
        quota = quota_commandes(pro)
        if quota['atteinte']:
            return Response({"error": "Vous avez atteint votre limite de commandes ce mois-ci.",
                             "code": "LIMITE_COMMANDES"}, status=403)

        with transaction.atomic():
            client = self._client_invite(cle, telephone, prenom, nom, d.get('genre'))
            moi = PersonneMesuree.moi(client)

            # Mesures prises à l'atelier : enregistrées sur la fiche du client
            figees = []
            for m in mesures:
                valeur = _decimal(m.get('valeur'))
                if valeur is None or valeur <= 0:
                    continue
                lib = None
                if m.get('libelle'):
                    lib = LibelleMesure.objects.filter(pk=m.get('libelle')).first()
                elif (m.get('nom') or '').strip():
                    n = m['nom'].strip()[:100]
                    lib = (LibelleMesure.objects.filter(professional_profile__isnull=True, client_profile__isnull=True, nom__iexact=n).first()
                           or LibelleMesure.objects.filter(professional_profile=pro, nom__iexact=n).first()
                           or LibelleMesure.objects.create(professional_profile=pro, nom=n))
                if lib is None:
                    continue
                MesureClient.objects.update_or_create(
                    client_profile=client, personne=moi, libelle=lib, defaults={"valeur": valeur})
                figees.append((lib.nom, valeur))

            commande = Commande.objects.create(
                client_profile=client, professional_profile=pro,
                total_commande=total, montant_paye=Decimal('0'), acompte_demande=acompte,
                statut_paiement='EN_ATTENTE', statut='En attente',
                date_livraison=date_livraison, creee_par_couturier=True,
                description=description or (modele.nom if modele else ''),
            )
            article = ModeleCommande.objects.create(
                commande=commande, modele_disponible=modele,
                image_personnalisee=d.get('image_personnalisee') or None,
                type_vetement=modele.type_vetement if modele else None,
                personne=moi, personne_nom='',
                prix_unitaire_snapshot=total,
            )
            ValeurMesureCommande.objects.bulk_create([
                ValeurMesureCommande(article_commande=article, libelle_nom=n, valeur=v) for n, v in figees])
            commande.jeton_suivi()

        return Response({
            "id": commande.id,
            "lien_suivi": url_suivi(request, commande),
            "message_whatsapp": message_whatsapp(request, commande),
            "lien_whatsapp": lien_whatsapp(request, commande),
        }, status=201)

    @staticmethod
    def _client_invite(cle, telephone, prenom, nom, genre):
        """Fiche client « sans appli » pour ce numéro (réutilisée d'une commande à l'autre)."""
        for cp in ClientProfile.objects.filter(invite=True, numero_telephone__endswith=cle[-8:]):
            if cle_telephone(cp.numero_telephone) == cle:
                champs = []
                if prenom and not cp.prenom:
                    cp.prenom = prenom; champs.append('prenom')
                if nom and not cp.nom:
                    cp.nom = nom; champs.append('nom')
                if champs:
                    cp.save(update_fields=champs)
                return cp
        user = User(username=f"invite_{uuid.uuid4().hex[:20]}", first_name=prenom, last_name=nom)
        user.set_unusable_password()
        user.save()
        g = str(genre or '').strip().upper()[:1]
        return ClientProfile.objects.create(user=user, prenom=prenom, nom=nom, numero_telephone=telephone,
                                            genre='Homme' if g == 'H' else 'Femme', invite=True)


# ------------------------------------------- 3. lien de suivi (couturier)
class LienSuiviView(APIView):
    """GET (couturier) : lien de suivi + message WhatsApp prêt à envoyer."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        pro = _pro(request)
        c = Commande.objects.select_related('client_profile', 'professional_profile').filter(
            pk=pk, professional_profile=pro).first() if pro else None
        if c is None:
            return Response({"error": "Commande introuvable."}, status=404)
        return Response({
            "lien_suivi": url_suivi(request, c),
            "message_whatsapp": message_whatsapp(request, c),
            "lien_whatsapp": lien_whatsapp(request, c),
            "telephone": c.client_profile.numero_telephone,
        })


# --------------------------------------------- 4. page web publique
@never_cache
def page_suivi(request, token):
    from commandes.views_suivi import ETAPES, ORDRE_ETAPES, _f
    c = (Commande.objects.select_related('professional_profile', 'client_profile')
         .prefetch_related('articles__modele_disponible').filter(lien_suivi=token).first())
    contexte = {
        "trouve": c is not None,
        "token": token,
        "play_store": LIEN_PLAY_STORE,
        "app_store": os.getenv("APP_STORE_URL", "").strip(),
        "lien_appli": f"dressmatter://s/{token}",
        "intent_android": (f"intent://s/{token}#Intent;scheme=dressmatter;package={PACKAGE_ANDROID};"
                           f"S.browser_fallback_url={quote(LIEN_PLAY_STORE, safe='')};end"),
    }
    if c is not None:
        rang = ORDRE_ETAPES.index(c.etape) if c.etape in ORDRE_ETAPES else 0
        pro = c.professional_profile
        art = c.articles.first()
        image = None
        if art:
            f = art.image_personnalisee or (art.modele_disponible.image if art.modele_disponible else None)
            if f:
                image = request.build_absolute_uri(f.url)
        contexte.update({
            "atelier": _nom_atelier(pro),
            "tel_atelier": pro.numero_telephone,
            "prenom": c.client_profile.prenom,
            "vetement": c.description or (art.modele_disponible.nom if art and art.modele_disponible else "Votre tenue"),
            "image": image,
            "numero": c.id,
            "date_livraison": c.date_livraison if c.creee_par_couturier or c.date_livraison else None,
            "etape_libelle": ETAPES.get(c.etape, c.etape),
            "etapes": [{"libelle": l, "faite": i < rang, "actuelle": i == rang}
                       for i, (_, l) in enumerate(Commande.ETAPES)],
            "total": _f(c.total_commande, c),
            "paye": _f(c.montant_paye, c),
            "reste": _f(c.reste_a_payer, c),
            "a_un_montant": (c.total_commande or 0) > 0,
            "date_essayage": c.date_essayage,
        })
    return render(request, 'suivi/page_suivi.html', contexte, status=200 if c else 404)


# ------------------------------------- 5. le client récupère ses commandes
def fusionner_client(invite, vrai):
    """Déplace commandes, personnes et mesures de la fiche « sans appli » vers le vrai compte."""
    for p in list(invite.personnes.all()):
        if p.est_moi:
            cible = PersonneMesuree.moi(vrai)
        else:
            cible = vrai.personnes.filter(prenom=p.prenom).first()
            if cible is None:
                p.client_profile = vrai
                p.save(update_fields=['client_profile'])
                MesureClient.objects.filter(personne=p).update(client_profile=vrai)
                continue
        for m in MesureClient.objects.filter(personne=p):
            existante = MesureClient.objects.filter(client_profile=vrai, personne=cible, libelle=m.libelle).first()
            if existante is None:
                m.client_profile, m.personne = vrai, cible
                m.save()
            elif m.derniere_mise_a_jour > existante.derniere_mise_a_jour:
                # La mesure prise par le couturier est plus récente : on la garde
                existante.valeur = m.valeur
                existante.save()
        ModeleCommande.objects.filter(personne=p).update(personne=cible)
    invite.commandes.update(client_profile=vrai)
    invite.avis_donnes.update(client_profile=vrai)
    if not vrai.numero_telephone and invite.numero_telephone:
        vrai.numero_telephone = invite.numero_telephone
        vrai.save(update_fields=['numero_telephone'])
    invite.user.delete()   # supprime aussi la fiche « sans appli », désormais vide


def _jeton_depuis(texte):
    texte = (texte or '').strip()
    m = re.search(r"/s/([A-Za-z0-9_\-]+)", texte)
    return m.group(1) if m else texte


class RecupererCommandesView(APIView):
    """POST (client connecté) {lien: "https://…/s/<jeton>/" ou le jeton seul}."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        vrai = getattr(request.user, 'client_profile', None)
        if vrai is None:
            return Response({"error": "Réservé aux comptes clients."}, status=403)
        c = Commande.objects.select_related('client_profile').filter(
            lien_suivi=_jeton_depuis(request.data.get('lien'))).first()
        if c is None:
            return Response({"error": "Lien de suivi introuvable."}, status=404)
        if c.client_profile_id == vrai.id:
            return Response({"message": "Cette commande est déjà dans votre compte.", "commandes": 0})
        if not c.client_profile.invite:
            return Response({"error": "Cette commande appartient déjà à un autre compte."}, status=403)

        # Lien prouvé : on rattache tout ce qui a été enregistré avec ce numéro
        cle = cle_telephone(c.client_profile.numero_telephone)
        fiches = [c.client_profile] + [
            cp for cp in ClientProfile.objects.filter(invite=True).exclude(pk=c.client_profile_id)
            .filter(numero_telephone__endswith=cle[-8:]) if cle and cle_telephone(cp.numero_telephone) == cle]
        nb = 0
        with transaction.atomic():
            for fiche in fiches:
                nb += fiche.commandes.count()
                fusionner_client(fiche, vrai)
        return Response({"message": f"{nb} commande(s) et vos mesures ont été ajoutées à votre compte.",
                         "commandes": nb})
