# ============================================================
#  Management Command : seed_commandes
#  Placer dans : commandes/management/commands/seed_commandes.py
#
#  Usage:
#    python manage.py seed_commandes             # 50 commandes
#    python manage.py seed_commandes --nb 100    # nombre custom
#    python manage.py seed_commandes --reset     # supprime et recrée
#    python manage.py seed_commandes --pro 2     # utilise le pro id=2
# ============================================================

import random
import uuid
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    ClientProfile,
    ProfessionalProfile,
    LibelleMesure,
    MesureClient,
    ModeleDisponible,
    TypeVetement,
    Commande,
    ModeleCommande,
    ValeurMesureCommande,
)

# ── Données fictives ivoiriennes ─────────────────────────────
NOMS = [
    "Konan", "Kouamé", "Bamba", "Touré", "Diallo", "Koffi",
    "Assi", "Ettien", "Lago", "Blé", "Sess", "N'Goran",
    "Coulibaly", "Traoré", "Koné", "Yao", "Wattara", "Fofana",
    "Keita", "Camara", "Dosso", "Diouf", "Gbagbo", "Soro",
]
PRENOMS_F = [
    "Marie", "Adjoua", "Ama", "Fatou", "Carine", "Mireille",
    "Akissi", "Sylvie", "Rosine", "Nadège", "Estelle", "Inès",
]
PRENOMS_M = [
    "Yves", "Kévin", "Paul", "Jean", "Brou", "Clément",
    "Olivier", "Patrick", "Serge", "Rodrigue", "Franck", "Yao",
]

MODELES_NOMS = [
    ("Boubou Grand Bazin",        "Boubou"),
    ("Robe Wax Élégante",         "Robe"),
    ("Costume Traditionnel",      "Costume"),
    ("Tenue de Mariage",          "Robe"),
    ("Ensemble Pagne",            "Ensemble"),
    ("Caftan Brodé",              "Caftan"),
    ("Robe Soirée Ankara",        "Robe"),
    ("Veste Africaine",           "Veste"),
    ("Jupe Wrap Kente",           "Jupe"),
    ("Dashiki Premium",           "Dashiki"),
    ("Tenue de Baptême",          "Ensemble"),
    ("Ensemble Wax Moderne",      "Ensemble"),
]

# (nom_libelle, min_cm, max_cm, pos_x, pos_y)
LIBELLES_STD = [
    ("Tour de poitrine",  88, 106, 50.0, 28.0),
    ("Tour de taille",    68,  90, 50.0, 45.0),
    ("Tour de hanches",   90, 110, 50.0, 58.0),
    ("Longueur dos",      38,  46, 50.0, 38.0),
    ("Longueur robe",     90, 130, 50.0, 70.0),
    ("Tour de cou",       34,  42, 50.0, 15.0),
    ("Longueur manche",   58,  68, 20.0, 40.0),
    ("Tour de bras",      28,  38, 15.0, 38.0),
]

STATUTS          = ["En attente", "En cours", "Terminées"]
MOYENS_PAIEMENT  = ["MOBILE_MONEY", "ESPECE", None]
TYPES_PAIEMENT   = ["TOTAL", "ACOMPTE", None]
GENRES           = ["homme", "femme"]


class Command(BaseCommand):
    help = "Insère N commandes de test réalistes (défaut : 50)."

    def add_arguments(self, parser):
        parser.add_argument("--nb",    type=int, default=50,
                            help="Nombre de commandes à créer (défaut: 50)")
        parser.add_argument("--reset", action="store_true",
                            help="Supprime toutes les commandes avant d'insérer")
        parser.add_argument("--pro",   type=int, default=None,
                            help="ID du ProfessionalProfile à utiliser")

    # ── Point d'entrée ────────────────────────────────────────
    def handle(self, *args, **options):
        nb    = options["nb"]
        reset = options["reset"]
        pro_id = options["pro"]

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n🪡  Seed Couturier Digital — {nb} commandes\n"
        ))

        if reset:
            n, _ = Commande.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"🗑  {n} commandes supprimées."))

        pro     = self._get_or_create_pro(pro_id)
        modeles = self._get_or_create_modeles(pro)
        self._ensure_libelles_std()

        ok = 0
        for i in range(nb):
            try:
                client  = self._get_or_create_client(i)
                self._ensure_mesures_client(client)
                cmd     = self._create_commande(client, pro, modeles)
                ok += 1
                self.stdout.write(
                    f"  ✅  #{cmd.id:>4}  {client.prenom} {client.nom:<14} "
                    f"{cmd.statut:<12}  {cmd.total_commande} FCFA"
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌  [{i}] {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"\n🎉  {ok} / {nb} commandes créées avec succès !\n"
        ))

    # ── Profil Professionnel ──────────────────────────────────
    def _get_or_create_pro(self, pro_id):
        if pro_id:
            try:
                pro = ProfessionalProfile.objects.get(pk=pro_id)
                self.stdout.write(f"  👔  Pro sélectionné : {pro.nom_entreprise}")
                return pro
            except ProfessionalProfile.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f"  ❌  Aucun ProfessionalProfile avec id={pro_id}."
                ))

        pro = ProfessionalProfile.objects.first()
        if pro:
            self.stdout.write(f"  👔  Pro trouvé : {pro.nom_entreprise}")
            return pro

        # Créer un pro de test minimal
        user, created = User.objects.get_or_create(
            username="pro_seed",
            defaults={"email": "pro_seed@couturier.ci",
                      "first_name": "Atelier", "last_name": "Seed"},
        )
        if created:
            user.set_password("Seed1234!")
            user.save()

        pro = ProfessionalProfile.objects.create(
            user=user,
            nom_entreprise="Atelier Couture Abidjan",
            nom="Seed", prenom="Pro",
            numero_telephone="+225070000001",
        )
        self.stdout.write(self.style.SUCCESS(
            f"  👔  Pro créé : {pro.nom_entreprise}  (login: pro_seed / Seed1234!)"
        ))
        return pro

    # ── Modèles disponibles ───────────────────────────────────
    def _get_or_create_modeles(self, pro):
        existing = list(ModeleDisponible.objects.filter(
            professional_profile=pro
        ))
        if existing:
            self.stdout.write(f"  👗  {len(existing)} modèles déjà présents.")
            return existing

        types_map = {}
        for _, type_nom in MODELES_NOMS:
            if type_nom not in types_map:
                t, _ = TypeVetement.objects.get_or_create(nom=type_nom)
                types_map[type_nom] = t

        created = []
        prix_choices = [15000, 20000, 25000, 35000, 45000, 55000]
        for nom, type_nom in MODELES_NOMS:
            prix    = Decimal(random.choice(prix_choices))
            acompte = (prix * Decimal("0.5")).quantize(Decimal("1"))
            m = ModeleDisponible.objects.create(
                professional_profile=pro,
                type_vetement=types_map[type_nom],
                nom=nom,
                description=f"Magnifique {nom.lower()} confectionné sur-mesure.",
                price=prix,
                acompte=acompte,
            )
            created.append(m)

        self.stdout.write(f"  👗  {len(created)} modèles créés.")
        return created

    # ── Libellés de mesure standards ──────────────────────────
    def _ensure_libelles_std(self):
        for nom, _, _, px, py in LIBELLES_STD:
            LibelleMesure.objects.get_or_create(
                client_profile=None,
                nom=nom,
                defaults={"position_x": px, "position_y": py,
                          "categorie": "Général"},
            )

    # ── Client de test ─────────────────────────────────────────
    def _get_or_create_client(self, index):
        genre  = random.choice(GENRES)
        prenom = random.choice(PRENOMS_F if genre == "femme" else PRENOMS_M)
        nom    = random.choice(NOMS)
        uname  = f"client_seed_{index:03d}"

        user, created = User.objects.get_or_create(
            username=uname,
            defaults={"email": f"{uname}@seed.ci",
                      "first_name": prenom, "last_name": nom},
        )
        if created:
            user.set_password("Seed1234!")
            user.save()

        profile, _ = ClientProfile.objects.get_or_create(
            user=user,
            defaults={"nom": nom, "prenom": prenom, "genre": genre},
        )
        return profile

    # ── Mesures du client ─────────────────────────────────────
    def _ensure_mesures_client(self, client):
        if MesureClient.objects.filter(client_profile=client).exists():
            return
        libelles = LibelleMesure.objects.filter(client_profile=None)
        bornes   = {nom: (mn, mx) for nom, mn, mx, *_ in LIBELLES_STD}
        MesureClient.objects.bulk_create([
            MesureClient(
                client_profile=client,
                libelle=lib,
                valeur=Decimal(random.randint(
                    *bornes.get(lib.nom, (60, 120))
                )),
            )
            for lib in libelles
        ])

    # ── Création d'une commande complète ──────────────────────
    def _create_commande(self, client, pro, modeles):
        # Sur-mesure 20 % du temps
        modele_dispo = None if random.random() < 0.2 else random.choice(modeles)

        prix    = modele_dispo.price   if modele_dispo else Decimal("0")
        acompte = modele_dispo.acompte if modele_dispo else Decimal("0")

        statut = random.choice(STATUTS)
        if statut == "Terminées":
            montant_paye   = prix
            statut_paie    = "TOTALEMENT_PAYE"
        elif prix > 0:
            montant_paye   = acompte
            statut_paie    = "ACOMPTE_PAYE"
        else:
            montant_paye   = Decimal("0")
            statut_paie    = "EN_ATTENTE"

        moyen_paiement = random.choice(MOYENS_PAIEMENT)
        type_paiement  = random.choice(TYPES_PAIEMENT)

        # Dates réalistes
        jours_passes   = random.randint(0, 60)
        date_creation  = timezone.now() - timedelta(days=jours_passes)
        date_livraison = timezone.now() + timedelta(days=random.randint(5, 45))

        # --- Commande ---
        commande = Commande.objects.create(
            client_profile       = client,
            professional_profile = pro,
            total_commande       = prix,
            acompte_demande      = acompte,
            montant_paye         = montant_paye,
            statut               = statut,
            statut_paiement      = statut_paie,
            moyen_paiement       = moyen_paiement,
            type_paiement        = type_paiement,
            date_livraison       = date_livraison,
        )
        # Forcer la date de création (auto_now_add non surchargeable)
        Commande.objects.filter(pk=commande.pk).update(
            date_creation=date_creation
        )

        # --- Article ---
        article = ModeleCommande.objects.create(
            commande              = commande,
            modele_disponible     = modele_dispo,
            prix_unitaire_snapshot= prix,
        )

        # --- Mesures figées ---
        mesures = MesureClient.objects.filter(client_profile=client).select_related("libelle")
        ValeurMesureCommande.objects.bulk_create([
            ValeurMesureCommande(
                article_commande=article,
                libelle_nom=m.libelle.nom,
                valeur=m.valeur,
            )
            for m in mesures
        ])

        return commande
