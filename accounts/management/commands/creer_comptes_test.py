"""
Crée (ou remet à jour) les deux comptes de test pour l'examen Google Play,
directement en base : pas d'inscription, pas de code par e-mail.

    python manage.py creer_comptes_test
    (Docker)  docker compose exec web python manage.py creer_comptes_test

On peut relancer la commande sans risque : elle ne crée pas de doublon et
remet les mots de passe à leur valeur ci-dessous.

Ce qui est créé :
- un compte CLIENT (Awa Kouassi) avec ses mesures de robe et de pantalon ;
- un compte COUTURIER (Atelier Démo Couture) avec 4 modèles et l'abonnement
  Premium actif pendant 1 an ;
- une commande du client chez le couturier, pour que le carnet ne soit pas vide.
"""
import io
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (Abonnement, ClientProfile, Commande, LibelleMesure, MesureClient,
                         ModeleCommande, ModeleDisponible, ProfessionalProfile, TypeVetement,
                         ValeurMesureCommande)

CLIENT = dict(username="test_client", email="test.client@treffcommunication.tech",
              password="Client2026!Test", nom="Kouassi", prenom="Awa", genre="F")
PRO = dict(username="test_couturier", email="test.couturier@treffcommunication.tech",
           password="Couturier2026!Test", nom="Traoré", prenom="Moussa",
           telephone="+2250700000001", atelier="Atelier Démo Couture")

MODELES = [  # nom, type, prix, avance, couleur de la photo
    ("Robe wax élégante", "Robe", 25000, 10000, (212, 83, 126)),
    ("Boubou bazin brodé", "Boubou", 45000, 20000, (29, 158, 117)),
    ("Pantalon classique", "Pantalon", 15000, 5000, (59, 110, 220)),
    ("Jupe pagne", "Jupe", 12000, 0, (186, 117, 23)),
]

MESURES_CLIENT = {  # clé de la bibliothèque -> valeur en cm
    "tour_cou": 34, "tour_poitrine": 92, "tour_taille": 74, "tour_hanches": 100,
    "carrure": 38, "longueur_robe": 105, "tour_cuisse": 58, "tour_genou": 38,
    "tour_cheville": 24, "longueur_pantalon": 100, "longueur_jupe": 65,
}


def image_tissu(couleur):
    """Petite image de tissu à motifs (pour que les modèles aient une photo)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (600, 800), couleur)
    d = ImageDraw.Draw(img)
    clair = tuple(min(255, c + 70) for c in couleur)
    for y in range(0, 800, 60):
        for x in range(0, 600, 60):
            d.ellipse([x + 12, y + 12, x + 48, y + 48], fill=clair)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return ContentFile(buf.getvalue())


class Command(BaseCommand):
    help = "Crée les comptes de test (client + couturier) pour l'examen Google Play."

    @transaction.atomic
    def handle(self, *args, **opts):
        # ── Couturier ───────────────────────────────────────────
        pu = self._user(PRO)
        pro = ProfessionalProfile.objects.filter(user=pu).first()
        if not pro:
            pro = ProfessionalProfile.objects.create(
                user=pu, nom_entreprise=PRO["atelier"], nom=PRO["nom"], prenom=PRO["prenom"],
                numero_telephone=PRO["telephone"])
        Abonnement.objects.update_or_create(
            professional_profile=pro, defaults={"date_fin": timezone.now() + timedelta(days=365)})

        modeles = []
        for nom, type_nom, prix, avance, couleur in MODELES:
            tv = TypeVetement.objects.filter(nom__iexact=type_nom, professional_profile__isnull=True).first()
            if tv is None:
                tv = TypeVetement.objects.create(nom=type_nom)
            m = ModeleDisponible.objects.filter(professional_profile=pro, nom=nom).first()
            if m is None:
                m = ModeleDisponible(professional_profile=pro, type_vetement=tv, nom=nom,
                                     description=f"{nom}, confectionné sur mesure.",
                                     price=Decimal(prix), acompte=Decimal(avance))
                m.image.save(f"demo_{nom.split()[0].lower()}_{random.randint(1000, 9999)}.jpg",
                             image_tissu(couleur), save=False)
                m.save()
            modeles.append(m)

        # ── Client ──────────────────────────────────────────────
        cu = self._user(CLIENT)
        client = ClientProfile.objects.filter(user=cu).first()
        if not client:
            client = ClientProfile.objects.create(user=cu, nom=CLIENT["nom"], prenom=CLIENT["prenom"],
                                                  genre=CLIENT["genre"])
        for cle, valeur in MESURES_CLIENT.items():
            lib = LibelleMesure.objects.filter(cle=cle, client_profile__isnull=True,
                                               professional_profile__isnull=True).first()
            if lib:
                MesureClient.objects.update_or_create(
                    client_profile=client, personne=None, libelle=lib, defaults={"valeur": Decimal(valeur)})

        # ── Une commande en cours (robe), si aucune n'existe ────
        if not Commande.objects.filter(client_profile=client, professional_profile=pro).exists():
            robe = modeles[0]
            cmd = Commande.objects.create(
                client_profile=client, professional_profile=pro,
                total_commande=robe.price, acompte_demande=robe.acompte, montant_paye=Decimal(0),
                statut="En attente", statut_paiement="EN_ATTENTE",
                date_livraison=timezone.now() + timedelta(days=12))
            art = ModeleCommande.objects.create(commande=cmd, modele_disponible=robe,
                                                prix_unitaire_snapshot=robe.price)
            for lib in robe.mesures_a_prendre():
                mc = MesureClient.objects.filter(client_profile=client, personne=None, libelle=lib).first()
                if mc:
                    ValeurMesureCommande.objects.create(article_commande=art, libelle_nom=lib.nom, valeur=mc.valeur)

        self.stdout.write(self.style.SUCCESS("\nComptes de test prêts :"))
        self.stdout.write(f"  CLIENT     {CLIENT['email']}  /  {CLIENT['password']}")
        self.stdout.write(f"  COUTURIER  {PRO['email']}  /  {PRO['password']}  (Premium jusqu'au "
                          f"{pro.abonnement.date_fin:%d/%m/%Y}, {len(modeles)} modèles)")

    def _user(self, d):
        u = User.objects.filter(email__iexact=d["email"]).first() or User.objects.filter(username=d["username"]).first()
        if u is None:
            u = User(username=d["username"], email=d["email"])
        u.email = d["email"]
        u.first_name, u.last_name = d["prenom"], d["nom"]
        u.is_active = True
        u.set_password(d["password"])
        u.save()
        return u
