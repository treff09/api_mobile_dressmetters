from django.views.decorators.cache import never_cache
# commandes/views.py

import uuid
from decimal import Decimal
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

# Imports de tes permissions et serializers
from accounts.permissions import IsClientOrReadOnly, IsProfessionalOrReadOnly
from .serializers import CommandeDetailSerializer, CommandeSerializer, CommandeStatusSerializer, MoyenPaiementSerializer, DefinirMontantSerializer

# Imports de tes modèles
from core.models import (
    Commande, ModeleCommande, Notification, OffreAbonnement, Abonnement,
    ValeurMesureCommande, MesureClient
)

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

# ============================================================
# 1. CRÉATION DE COMMANDE (LOGIQUE DE CAPTURE FIGÉE)
# ============================================================
from decimal import Decimal
import uuid
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from core.models import (
    Commande, ModeleCommande, Notification, 
    ValeurMesureCommande, MesureClient
)
# Assure-toi d'importer ton CommandeSerializer mis à jour
# from .serializers import CommandeSerializer 

from decimal import Decimal
import uuid
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

# Imports pour les notifications
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class CommandeCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        data = request.data.copy()

        # 1. HACK MULTIPART : Reconstruction de la liste d'articles
        articles = []
        i = 0
        while f'articles[{i}]modele_disponible' in data or f'articles[{i}]image_personnalisee' in data:
            modele_id = data.get(f'articles[{i}]modele_disponible')
            
            # Nettoyage pour le sur-mesure
            if modele_id in ["0", "", "null", None]:
                modele_id = None
                
            type_id = data.get(f'articles[{i}]type_vetement')
            if type_id in ["0", "", "null", None]:
                type_id = None
            article = {
                'modele_disponible': modele_id,
                'image_personnalisee': data.get(f'articles[{i}]image_personnalisee'),
                'type_vetement': type_id,
            }
            # Photo du tissu envoyée directement avec la commande (facultative)
            if data.get(f'articles[{i}]image_tissu'):
                article['image_tissu'] = data.get(f'articles[{i}]image_tissu')
            articles.append(article)
            i += 1
        
        if articles:
            data.setlist('articles', articles)

        serializer = CommandeSerializer(data=data, context={'request': request})
        
        if serializer.is_valid():
            articles_data = serializer.validated_data.get('articles', [])

            # Couturier parti ou modèle retiré du catalogue : on ne peut plus commander
            pro_cible = serializer.validated_data.get('professional_profile')
            if pro_cible and not pro_cible.user.is_active:
                return Response({"error": "Ce couturier n'est plus disponible."}, status=400)
            for art in articles_data:
                m = art.get('modele_disponible')
                if m and not m.actif:
                    return Response({"error": f"Le modèle « {m.nom} » n'est plus proposé par le couturier."}, status=400)
            client_user = request.user
            
            # Vérifications de sécurité
            if not hasattr(client_user, 'client_profile'):
                return Response({"error": "Profil client requis."}, status=400)
            
            client_profile = client_user.client_profile

            # Pour qui est la commande (Moi, Junior…). Sans précision : « Moi ».
            from core.models import PersonneMesuree
            personne_id = request.data.get('personne')
            if personne_id in (None, '', '0', 'null'):
                personne = PersonneMesuree.moi(client_profile)
            else:
                personne = client_profile.personnes.filter(pk=personne_id).first()
                if personne is None:
                    return Response({"error": "Personne introuvable."}, status=400)

            # 2. Calcul financier (informatif uniquement : le règlement se fait
            # désormais hors-app, via Mobile Money ou Espèce, choisi juste après)
            prix_total = Decimal('0.00')
            acompte_demande = Decimal('0.00')
            for art in articles_data:
                modele = art.get('modele_disponible')
                if modele:
                    prix_total += Decimal(str(modele.price))
                    # L'acompte est décidé par le couturier lui-même sur chaque
                    # modèle (plus de calcul automatique à 50%).
                    acompte_demande += Decimal(str(modele.acompte or 0))
                # Pour un article sur-mesure (sans modele_disponible), aucun
                # acompte n'est calculé automatiquement : le couturier le
                # communique directement au client (devis).

            # 3. Vérification Mesures
            mesures_profil = MesureClient.objects.filter(
                client_profile=client_profile, personne=personne).select_related('libelle')
            if not mesures_profil.exists():
                return Response({"error": "Il faut d'abord prendre tes mesures." if personne.est_moi else f"Il faut d'abord prendre les mesures de {personne.prenom}.",
                                 "mesures_manquantes": []}, status=400)

            def mesures_requises(art):
                """Mesures à demander : celles du modèle, sinon celles du type choisi (sur-mesure)."""
                m = art.get('modele_disponible')
                if m:
                    return list(m.mesures_a_prendre())
                tv = art.get('type_vetement')
                if tv:
                    return list(tv.mesures_requises.all())
                return []

            # Mesures demandées par chaque modèle (mode guidé) : toutes doivent être connues
            valeurs_connues = {m.libelle_id for m in mesures_profil if m.valeur and m.valeur > 0}
            manquantes = []
            for art in articles_data:
                for lib in mesures_requises(art):
                    if lib.id not in valeurs_connues and lib.nom not in manquantes:
                        manquantes.append(lib.nom)
            if manquantes:
                return Response({
                    "error": "Il manque des mesures pour ce modèle.",
                    "mesures_manquantes": manquantes,
                }, status=400)

            try:
                with transaction.atomic():
                    # 4. Création de la Commande
                    # Aucun montant n'est prélevé automatiquement : le client
                    # choisit son moyen de paiement (Mobile Money / Espèce)
                    # juste après la validation de sa commande.
                    pro_profile = serializer.validated_data['professional_profile']
                    commande = Commande.objects.create(
                        client_profile=client_profile,
                        professional_profile=pro_profile,
                        total_commande=prix_total,
                        montant_paye=Decimal('0.00'),
                        acompte_demande=acompte_demande,
                        statut_paiement='EN_ATTENTE',
                        statut='En attente',
                        date_livraison=serializer.validated_data.get('date_livraison')
                    )

                    # 5. Création des Articles (Le signal s'occupera du reste)
                    for art_data in articles_data:
                        modele_dispo = art_data.get('modele_disponible')
                        mesures_manuelles = art_data.get('mesures', [])

                        modele_commande = ModeleCommande.objects.create(
                            commande=commande,
                            modele_disponible=modele_dispo,
                            image_personnalisee=art_data.get('image_personnalisee'),
                            image_tissu=art_data.get('image_tissu'),
                            type_vetement=art_data.get('type_vetement'),
                            personne=personne,
                            personne_nom='' if personne.est_moi else personne.prenom,
                            prix_unitaire_snapshot=modele_dispo.price if modele_dispo else Decimal('0.00')
                        )

                        # Le signal est désactivé, on gère tout ici
                        if mesures_manuelles:
                            # Cas 1 : le client a saisi ses propres mesures pour cet article
                            ValeurMesureCommande.objects.bulk_create([
                                ValeurMesureCommande(
                                    article_commande=modele_commande,
                                    libelle_nom=m['libelle_nom'],
                                    valeur=m['valeur']
                                ) for m in mesures_manuelles
                            ])
                        else:
                            # Cas 2 : on capture (fige) une COPIE des mesures du profil à cet instant
                            # Ces données ne changeront JAMAIS même si le client modifie son profil après.
                            # Si le modèle définit ses mesures, on ne fige QUE celles-là.
                            a_figer = mesures_profil
                            ids_requis = {lib.id for lib in mesures_requises(art_data)}
                            if ids_requis:
                                a_figer = [m for m in mesures_profil if m.libelle_id in ids_requis]
                            ValeurMesureCommande.objects.bulk_create([
                                ValeurMesureCommande(
                                    article_commande=modele_commande,
                                    libelle_nom=m.libelle.nom,  # copie du nom (string), pas une FK
                                    valeur=m.valeur             # copie de la valeur (decimal), pas une FK
                                )
                                for m in a_figer
                            ])

                    # 6. ENVOI DES NOTIFICATIONS (Après le succès de la transaction)
                    self._send_order_notification(pro_profile.user, commande, client_user.username)

                return Response({"message": "Commande validée !", "commande_id": commande.id}, status=201)

            except Exception as e:
                return Response({"error": f"Erreur technique : {str(e)}"}, status=500)
        
        print(f"Erreurs Serializer : {serializer.errors}")
        return Response(serializer.errors, status=400)

    def _send_order_notification(self, user, commande, client_name):
        """Gère la création en DB et l'envoi en temps réel via WebSockets"""
        try:
            channel_layer = get_channel_layer()
            msg_pro = f"Nouvelle commande #{commande.id} reçue de {client_name}."
            
            # 1. Sauvegarde en Base de Données
            Notification.objects.create(
                user=user, 
                title="Nouvelle Commande", 
                message=msg_pro, 
                commande_id=commande.id
            )
            
            # 2. Envoi via Channels (WebSocket)
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user.id}",
                    {
                        "type": "send_notification",
                        "data": {
                            "type": "NEW_ORDER", 
                            "title": "Couture", 
                            "message": msg_pro, 
                            "commande_id": commande.id
                        }
                    }
                )
        except Exception as e:
            print(f"Erreur lors de l'envoi de la notification : {e}")
# ============================================================
# 1bis. CHOIX DU MOYEN DE PAIEMENT (APRÈS LA COMMANDE)
# ============================================================
class CommandeChoisirPaiementView(APIView):
    """
    Appelée juste après la création d'une commande : le client choisit
    comment il compte régler auprès du professionnel (Mobile Money ou
    Espèce). Aucun mouvement de points n'est effectué ici : le paiement
    réel se fait hors-app, ceci ne fait qu'informer le professionnel.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            commande = Commande.objects.get(pk=pk)
        except Commande.DoesNotExist:
            return Response({"error": "Commande introuvable."}, status=404)

        # Seul le client propriétaire de la commande peut choisir son moyen de paiement
        if not hasattr(request.user, 'client_profile') or commande.client_profile != request.user.client_profile:
            return Response({"error": "Non autorisé."}, status=403)

        serializer = MoyenPaiementSerializer(commande, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()

            # 🔹 Montant indicatif que le client compte régler (aucun mouvement
            # d'argent réel) : la totalité, ou seulement l'acompte fixé par le
            # couturier. Si le prix n'est pas encore connu (commande sur-mesure,
            # en attente que le couturier fixe son montant), on ne peut pas
            # encore calculer ce montant : ce sera fait automatiquement dès que
            # le couturier renseignera le prix (voir CommandeDefinirMontantView).
            if commande.total_commande and commande.total_commande > 0 and commande.type_paiement:
                if commande.type_paiement == 'ACOMPTE':
                    commande.montant_paye = commande.acompte_demande or Decimal('0.00')
                else:
                    commande.montant_paye = commande.total_commande
                commande.save()

            # Notifie le professionnel du moyen de paiement choisi
            try:
                moyen_label = dict(Commande.MOYEN_PAIEMENT_CHOICES).get(commande.moyen_paiement, commande.moyen_paiement)
                type_label = dict(Commande.TYPE_PAIEMENT_CHOICES).get(commande.type_paiement, '')
                pro_user = commande.professional_profile.user
                msg = f"Le client a choisi de régler la commande #{commande.id} par {moyen_label}"
                msg += f" ({type_label})." if type_label else "."
                Notification.objects.create(user=pro_user, title="Moyen de paiement", message=msg, commande_id=commande.id)

                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{pro_user.id}",
                        {
                            "type": "send_notification",
                            "data": {
                                "type": "PAYMENT_METHOD_CHOSEN",
                                "title": "Couture",
                                "message": msg,
                                "commande_id": commande.id,
                            }
                        }
                    )
            except Exception as e:
                print(f"Erreur notification moyen de paiement : {e}")

            return Response({
                "message": "Moyen de paiement enregistré.",
                "moyen_paiement": commande.moyen_paiement,
                "type_paiement": commande.type_paiement,
                "montant_paye": commande.montant_paye,
            }, status=200)

        return Response(serializer.errors, status=400)


# ============================================================
# 1ter. DÉFINITION DU MONTANT (COMMANDES SUR-MESURE)
# ============================================================
class CommandeDefinirMontantView(APIView):
    """
    Quand le client envoie une image personnalisée (sur-mesure, sans modèle
    catalogue), le prix n'est pas connu à la création de la commande.
    Cette vue permet au PROFESSIONNEL propriétaire de la commande d'indiquer
    le montant qu'il facture pour la confection. Ce montant est ensuite
    visible par le client dans le détail de sa commande, et doit être défini
    avant de pouvoir marquer la commande comme terminée/livrée.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            commande = Commande.objects.get(pk=pk)
        except Commande.DoesNotExist:
            return Response({"error": "Commande introuvable."}, status=404)

        # Seul le professionnel propriétaire de la commande peut fixer le montant
        if not hasattr(request.user, 'professional_profile') or commande.professional_profile != request.user.professional_profile:
            return Response({"error": "Non autorisé."}, status=403)

        serializer = DefinirMontantSerializer(commande, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()  # déclenche Commande.save() -> recalcule reste_a_payer

            # 🔹 Si le client avait déjà choisi (avant que le prix soit connu)
            # de payer la totalité ou l'acompte, on peut maintenant calculer
            # le montant indicatif correspondant.
            if commande.type_paiement:
                if commande.type_paiement == 'ACOMPTE':
                    commande.montant_paye = commande.acompte_demande or Decimal('0.00')
                else:
                    commande.montant_paye = commande.total_commande
                commande.save()

            # Notifie le client du montant fixé par le couturier
            try:
                client_user = commande.client_profile.user
                msg = f"Le montant de votre commande #{commande.id} a été fixé à {commande.total_commande} FCFA."
                Notification.objects.create(user=client_user, title="Montant de la commande", message=msg, commande_id=commande.id)

                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{client_user.id}",
                        {
                            "type": "send_notification",
                            "data": {
                                "type": "PRICE_SET",
                                "title": "Couture",
                                "message": msg,
                                "commande_id": commande.id,
                            }
                        }
                    )
            except Exception as e:
                print(f"Erreur notification montant défini : {e}")

            return Response({
                "message": "Montant enregistré.",
                "total_commande": commande.total_commande,
                "reste_a_payer": commande.reste_a_payer,
            }, status=200)

        return Response(serializer.errors, status=400)


# ============================================================
# 2. MISES À JOUR DE STATUT & PAIEMENT FINAL
# ============================================================

class CommandeUpdateStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            commande = Commande.objects.get(pk=pk)
            nouveau_statut = request.data.get('statut')
            client_user = commande.client_profile.user
            channel_layer = get_channel_layer()

            # Le Flutter envoie 'Terminée' (l'app pro) — on reste tolérant sur
            # l'orthographe/l'accord pour ne rater aucun cas.
            est_terminee = (nouveau_statut or '').strip().lower() in (
                'terminée', 'terminées', 'termine', 'termines', 'livrée', 'livree'
            )

            # --- LOGIQUE POUR LA LIVRAISON ---
            if est_terminee:
                # 🔒 Commande sur-mesure (image envoyée par le client, sans
                # modèle catalogue) : le professionnel doit avoir fixé son
                # montant AVANT de pouvoir marquer la commande comme terminée.
                if commande.total_commande is None or commande.total_commande <= 0:
                    return Response({
                        "error": "Montant non défini",
                        "detail": "Veuillez d'abord indiquer le montant de la commande (confection sur-mesure) avant de la marquer comme terminée."
                    }, status=400)

                # Le règlement (Mobile Money / Espèce) se fait désormais hors-app,
                # directement entre le client et le professionnel : on ne touche
                # plus aux portefeuilles ici, on marque simplement la commande
                # comme totalement payée/livrée.
                with transaction.atomic():
                    commande.montant_paye = commande.total_commande
                    commande.statut = 'Terminées'
                    commande.statut_paiement = 'TOTALEMENT_PAYE'
                    commande.save()

            else:
                # Changement de statut simple (En cours, etc.)
                commande.statut = nouveau_statut
                commande.save()

            # --- ENVOI DE NOTIFICATION AU CLIENT (DB + WEBSOCKET) ---
            msg_text = f"Votre commande #{commande.id} est maintenant : {nouveau_statut}"
            Notification.objects.create(user=client_user, title="Statut Commande", message=msg_text, commande_id=commande.id)
            
            async_to_sync(channel_layer.group_send)(
                f"user_{client_user.id}",
                {
                    "type": "send_notification",
                    "data": {"type": "STATUS_UPDATE", "title": "Commande", "message": msg_text, "commande_id": commande.id}
                }
            )

            return Response({"message": "Statut mis à jour."}, status=200)

        except Commande.DoesNotExist:
            return Response({"error": "Commande introuvable"}, status=404)


# ============================================================
# 3. LISTES DES COMMANDES
# ============================================================

class CommandeListByProfessionalView(ListAPIView):
    serializer_class = CommandeDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # On cherche les commandes liées au profil pro de l'utilisateur connecté
        # On utilise '__user' pour être sûr de pointer sur le bon compte
        return Commande.objects.filter(
            professional_profile__user=user
        ).order_by('-date_creation')

class CommandeListByClientView(ListAPIView):
    serializer_class = CommandeDetailSerializer
    permission_classes = [IsAuthenticated, IsClientOrReadOnly]

    def get_queryset(self):
        if not hasattr(self.request.user, 'client_profile'):
            return Commande.objects.none()
        return Commande.objects.filter(
            client_profile=self.request.user.client_profile
        ).order_by('-date_creation')

# ============================================================
# TRAITEMENT DES ABONNEMENTS ET DU PAIEMENT HORS-APP (WEB)
# ============================================================
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from datetime import timedelta


def landing_page_view(request):
    """
    Site vitrine (page d'accueil publique du site web) : explique à quoi
    sert l'application et propose de se connecter (réservé aux comptes
    professionnels) pour gérer son abonnement.
    """
    return render(request, 'landing/landing.html')


def web_login_view(request):
    """
    Vue de connexion Web standard (Style Spotify).
    Réservée aux COMPTES PROFESSIONNELS uniquement : les clients n'ont pas
    accès à cet espace (gestion d'abonnement / recharge).
    Une fois connecté, redirige automatiquement vers la page de recharge.
    """
    error_message = None

    if request.user.is_authenticated:
        if hasattr(request.user, 'professional_profile'):
            return redirect('web_recharge')
        # Un client est connecté par erreur : on le déconnecte et on bloque l'accès.
        auth_logout(request)

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if not hasattr(user, 'professional_profile'):
                error_message = "Cet espace est réservé aux comptes professionnels. Utilisez l'application mobile pour votre compte client."
                form = AuthenticationForm()
            else:
                auth_login(request, user)
                # Redirige vers la page de recharge après connexion réussie
                return redirect('web_recharge')
    else:
        form = AuthenticationForm()

    return render(request, 'registration/web_login.html', {
        'form': form,
        'error_message': error_message,
    })


@login_required(login_url='/accounts/web-login/')
def web_recharge_view(request):
    """
    Espace Compte Web sécurisé : le professionnel y consulte son abonnement
    et peut l'activer/le renouveler. Aucun wallet ni solde de points : les
    offres sont affichées en FCFA, l'activation se fait directement (le
    règlement réel par Mobile Money sera intégré plus tard).
    Réservé aux comptes PROFESSIONNELS.
    """
    user = request.user
    
    if not user.is_authenticated or user.is_anonymous:
        return redirect('web_login')

    # 🔒 Un client ne doit jamais atteindre cette page (même en devinant l'URL).
    if not hasattr(user, 'professional_profile'):
        auth_logout(request)
        return redirect('web_login')

    pro_profile = user.professional_profile

    # 🎯 On récupère les vraies offres depuis le modèle Django
    db_offers = OffreAbonnement.objects.filter(actif=True).order_by('prix')
    offers = [
        {"id": offer.id, "nom": offer.nom, "prix": offer.prix, "duree_jours": offer.duree_jours}
        for offer in db_offers
    ]

    abonnement = getattr(pro_profile, 'abonnement', None)

    context = {
        'username': user.username,
        'email': user.email,
        'entreprise': pro_profile.nom_entreprise,
        'offers': offers,
        'abonnement_actif': abonnement.est_actif if abonnement else False,
        'date_fin_abonnement': abonnement.date_fin if abonnement else None,
        'jours_restants': abonnement.jours_restants if abonnement else None,
        'offre_actuelle': abonnement.offre if abonnement else None,
    }
    return render(request, 'payments/web_recharge.html', context)


@login_required(login_url='/accounts/web-login/')
def web_activer_abonnement_view(request, offre_id):
    """
    Active (ou prolonge) l'abonnement du professionnel pour l'offre choisie.
    Aucun wallet/point n'intervient : pour l'instant l'activation est directe
    (le règlement réel par Mobile Money sera branché ici plus tard).
    """
    user = request.user
    if not user.is_authenticated or not hasattr(user, 'professional_profile'):
        return redirect('web_login')

    if request.method != 'POST':
        return redirect('web_recharge')

    pro_profile = user.professional_profile
    offre = get_object_or_404(OffreAbonnement, id=offre_id)
    now = timezone.now()

    with transaction.atomic():
        abonnement, created = Abonnement.objects.get_or_create(
            professional_profile=pro_profile,
            defaults={'offre': offre, 'date_fin': now}
        )

        # Si un abonnement est déjà actif, on prolonge à partir de sa date de
        # fin actuelle plutôt que de repartir de zéro.
        if not created and abonnement.date_fin and abonnement.date_fin > now:
            nouvelle_date_fin = abonnement.date_fin + timedelta(days=offre.duree_jours)
        else:
            nouvelle_date_fin = now + timedelta(days=offre.duree_jours)

        abonnement.offre = offre
        abonnement.date_fin = nouvelle_date_fin
        abonnement.save()

    return redirect('web_recharge')

"""
Remplace l'ancienne web_activer_abonnement_view (activation directe sans
paiement réel) par un vrai flux en 3 étapes, à coller dans commandes/views.py
à la place de la fonction existante.

1. web_payer_abonnement_view   : choix opérateur + numéro, initie le paiement
2. web_paiement_attente_view   : page d'attente qui poll la confirmation (JS)
3. web_confirmer_paiement_view : endpoint JSON pollé par la page d'attente,
   n'active l'abonnement qu'au moment où la gateway confirme SUCCESSFUL

⚠️ Ne gère que mtn_momo et orange_money (flux "push", validation sur le
téléphone). Wave (flux redirection) demande une petite extension de la
gateway avant de pouvoir être branché ici proprement -- voir le README.
"""

from core.gateway_client import GatewayError, check_status, generate_order_id, initiate_payment
from core.models import AbonnementPaiement

PUSH_PROVIDERS = {"mtn_momo": "MTN MoMo", "orange_money": "Orange Money"}


def strip_225_prefix(raw_number):
    """Pour l'affichage : retire un éventuel préfixe 225/+225 déjà stocké."""
    number = (raw_number or "").strip().replace(" ", "").replace("-", "")
    if number.startswith("+225"):
        return number[4:]
    if number.startswith("225"):
        return number[3:]
    return number


def build_phone_number(phone_local):
    """
    Combine le préfixe fixe 225 avec la partie saisie par l'utilisateur --
    mais UNIQUEMENT si ça ressemble à un numéro local ivoirien (commence
    par 0, ex. "0700000000" -> "2250700000000").

    Si l'utilisateur tape un numéro déjà complet/international (ex. les
    numéros de test sandbox MTN comme "46733123450", qui ne commencent pas
    par 0), on ne préfixe RIEN et on l'envoie tel quel. Sans ce garde-fou,
    "46733123450" deviendrait "22546733123450", qui ne correspond à aucun
    des numéros de test MTN -> le sandbox renvoie alors toujours SUCCESSFUL,
    rendant impossible de tester un échec.
    """
    local = (phone_local or "").strip().replace(" ", "").replace("-", "")
    if local.startswith("+225"):
        return local[1:]  # "+2250700000000" -> "2250700000000"
    if local.startswith("225"):
        return local
    if local.startswith("0"):
        return f"225{local}"
    # Ne commence pas par 0 -> considéré comme déjà complet (numéro
    # international réel, ou numéro de test sandbox) : envoyé tel quel.
    return local


from rechargements.models import PaiementChariow
from rechargements.views_chariow import PaiementImpossible, demarrer_paiement_chariow, statut_pour_page_attente


def _url_retour_chariow(request):
    """
    Adresse où Chariow renvoie l'acheteur après paiement. Chariow n'accepte qu'une adresse publique :
    - site en ligne (https, vrai domaine) -> page d'attente de CE paiement ;
    - test en local (127.0.0.1, localhost, http) -> CHARIOW_REDIRECT_URL du .env, sinon page par défaut de Chariow.
    """
    from urllib.parse import urlparse
    from django.conf import settings
    base = request.build_absolute_uri('/')
    hote = urlparse(base).hostname or ''
    local = hote in ('localhost', '127.0.0.1', '0.0.0.0') or hote.startswith('192.168.') or hote.startswith('10.') or '.' not in hote
    if base.startswith('https://') and not local:
        return base.rstrip('/') + '/payments/attente/{ref}/'
    return settings.CHARIOW_REDIRECT_URL or None


@login_required(login_url='/accounts/web-login/')
def web_payer_abonnement_view(request, offre_id):
    """
    GET  : récapitulatif de la formule + numéro de téléphone
    POST : crée le paiement Chariow et redirige vers la page de paiement Chariow.
           Chariow ramène ensuite l'utilisateur sur la page d'attente.
    L'abonnement n'est JAMAIS activé ici : seul le webhook Chariow le fait.
    """
    user = request.user
    if not hasattr(user, 'professional_profile'):
        auth_logout(request)
        return redirect('web_login')

    pro_profile = user.professional_profile
    offre = get_object_or_404(OffreAbonnement, id=offre_id, actif=True)
    contexte = {'offre': offre, 'default_phone_local': strip_225_prefix(pro_profile.numero_telephone or '')}

    if request.method == 'GET':
        return render(request, 'payments/web_payer.html', contexte)

    phone_local = request.POST.get('phone_local', '').strip()
    contexte['default_phone_local'] = phone_local
    if not phone_local:
        contexte['error'] = "Le numéro de téléphone est requis."
        return render(request, 'payments/web_payer.html', contexte)

    telephone = phone_local if phone_local.startswith('+') else '+' + build_phone_number(phone_local)
    try:
        # Après paiement, Chariow ramène l'utilisateur sur la page d'attente de CE paiement
        paiement = demarrer_paiement_chariow(request, pro_profile, offre, telephone,
                                             redirect_url=_url_retour_chariow(request))
    except PaiementImpossible as e:
        contexte['error'] = str(e)
        return render(request, 'payments/web_payer.html', contexte)
    return redirect(paiement.checkout_url)


@login_required(login_url='/accounts/web-login/')
def web_paiement_attente_view(request, order_id):
    """
    Page d'attente après le paiement : interroge web_confirmer_paiement_view toutes les 3 s.
    Références « DM-… » = Chariow ; les autres = ancienne gateway (historique).
    """
    pro = request.user.professional_profile
    if order_id.startswith('DM-'):
        paiement = get_object_or_404(PaiementChariow, reference=order_id, professional_profile=pro)
        return render(request, 'payments/web_attente.html',
                      {'order_id': order_id, 'provider_label': 'Chariow', 'offre': paiement.offre, 'chariow': True})
    paiement = get_object_or_404(AbonnementPaiement, order_id=order_id, professional_profile=pro)
    return render(request, 'payments/web_attente.html', {
        'order_id': order_id,
        'provider_label': PUSH_PROVIDERS.get(paiement.provider, paiement.provider),
        'offre': paiement.offre,
    })


@never_cache
@login_required(login_url='/accounts/web-login/')
def web_confirmer_paiement_view(request, order_id):
    """
    Endpoint JSON pollé par la page d'attente.
    Chariow : lecture seule du statut posé par le webhook (aucune activation ici).
    """
    pro = request.user.professional_profile
    if order_id.startswith('DM-'):
        paiement = get_object_or_404(PaiementChariow, reference=order_id, professional_profile=pro)
        return JsonResponse(statut_pour_page_attente(paiement))

    # --- Ancienne gateway (paiements historiques) ---
    paiement = get_object_or_404(AbonnementPaiement, order_id=order_id, professional_profile=pro)

    if paiement.applied:
        abonnement = pro.abonnement
        return JsonResponse({
            'status': 'SUCCESSFUL',
            'expire_le': abonnement.date_fin.strftime("%d/%m/%Y"),
            'jours_restants': abonnement.jours_restants,
        })

    try:
        gateway_response = check_status(order_id)
    except GatewayError as exc:
        return JsonResponse({'status': 'ERROR', 'error': str(exc)}, status=502)

    gateway_status = gateway_response.get('status', 'PENDING')
    paiement.status = gateway_status
    paiement.save(update_fields=['status', 'updated_at'])

    if gateway_status in ('PENDING', 'FAILED'):
        return JsonResponse({'status': gateway_status})

    # SUCCESSFUL -> activation/prolongation, une seule fois
    offre = paiement.offre
    now = timezone.now()
    with transaction.atomic():
        abonnement, created = Abonnement.objects.get_or_create(
            professional_profile=pro, defaults={'offre': offre, 'date_fin': now}
        )
        if not created and abonnement.date_fin and abonnement.date_fin > now:
            nouvelle_date_fin = abonnement.date_fin + timedelta(days=offre.duree_jours)
        else:
            nouvelle_date_fin = now + timedelta(days=offre.duree_jours)
        abonnement.offre = offre
        abonnement.date_fin = nouvelle_date_fin
        abonnement.save()
        paiement.applied = True
        paiement.save(update_fields=['applied', 'updated_at'])

    return JsonResponse({
        'status': 'SUCCESSFUL',
        'message': f'Offre {offre.nom} activée',
        'expire_le': nouvelle_date_fin.strftime("%d/%m/%Y"),
        'jours_restants': abonnement.jours_restants,
    })

# ============================================================
# UPLOAD PHOTO TISSU — Ajouter/remplacer l'image d'un article
# PATCH /api/v1/commandes/<commande_pk>/articles/<article_pk>/upload-tissu/
# ============================================================
from rest_framework.parsers import MultiPartParser, FormParser

class UploadTissuImageView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request, commande_pk, article_pk):
        try:
            commande = Commande.objects.get(pk=commande_pk)
        except Commande.DoesNotExist:
            return Response({'error': 'Commande introuvable.'}, status=404)

        # Vérification : seul le client ou le pro concerné peut uploader
        user = request.user
        is_client = hasattr(user, 'client_profile') and \
                    commande.client_profile == user.client_profile
        is_pro = hasattr(user, 'professional_profile') and \
                 commande.professional_profile == user.professional_profile

        if not (is_client or is_pro):
            return Response({'error': 'Accès refusé.'}, status=403)

        try:
            article = commande.articles.get(pk=article_pk)
        except Exception:
            return Response({'error': 'Article introuvable.'}, status=404)

        image = request.FILES.get('image_tissu')
        if not image:
            return Response({'error': 'Aucune image fournie. Champ attendu : image_tissu'}, status=400)

        # Valider le type de fichier
        allowed_types = [
            'image/jpeg', 'image/jpg', 'image/png', 'image/webp',
            'image/gif', 'image/heic', 'image/heif',
            'application/octet-stream',  # fallback camera Android
        ]
        # Vérification par extension si le content_type est inconnu
        ext = image.name.split('.')[-1].lower() if '.' in image.name else ''
        allowed_exts = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'heic', 'heif']
        if image.content_type not in allowed_types and ext not in allowed_exts:
            return Response(
                {'error': f'Format non supporte ({image.content_type}). Utilisez JPEG, PNG ou WebP.'},
                status=400
            )

        # Supprimer l'ancienne photo tissu si elle existe
        if article.image_tissu:
            try:
                article.image_tissu.delete(save=False)
            except Exception:
                pass

        # Sauvegarder dans commandes/tissu/
        article.image_tissu = image
        article.save()

        return Response({
            'message': 'Photo du tissu sauvegardée dans commandes/tissu/.',
            'image_tissu_url': request.build_absolute_uri(article.image_tissu.url),
        }, status=200)
