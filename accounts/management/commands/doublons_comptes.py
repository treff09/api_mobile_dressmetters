"""
Trouve et règle les comptes en double.

1. Plusieurs comptes avec le même e-mail (sans tenir compte des majuscules) :
   on GARDE le compte le plus utilisé (commandes, modèles, mesures ; à égalité,
   le dernier connecté). Les autres sont mis EN PAUSE (rien n'est effacé) et leur
   e-mail est remplacé par doublon_<id>@doublon.invalid. Chaque mise en pause est
   notée dans l'admin (Départs des comptes) avec l'e-mail d'origine.

2. Un même compte à la fois client ET couturier :
   si l'un des deux profils est vide (aucune commande, aucun modèle, aucune mesure),
   il est supprimé. Si les deux sont utilisés, le compte est seulement signalé :
   à traiter à la main.

    python manage.py doublons_comptes              # affiche seulement (rien ne change)
    python manage.py doublons_comptes --appliquer  # applique les corrections
"""
from collections import defaultdict

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.functions import Lower

from core.models import (ClientProfile, Commande, DepartCompte, MesureClient, ModeleDisponible,
                         ProfessionalProfile)


def activite(user):
    """Nombre d'éléments rattachés au compte (plus c'est grand, plus il est utilisé)."""
    n = 0
    client = ClientProfile.objects.filter(user=user).first()
    pro = ProfessionalProfile.objects.filter(user=user).first()
    if client:
        n += Commande.objects.filter(client_profile=client).count()
        n += MesureClient.objects.filter(client_profile=client).count()
    if pro:
        n += Commande.objects.filter(professional_profile=pro).count()
        n += ModeleDisponible.objects.filter(professional_profile=pro).count()
    return n


def role(user):
    r = []
    if ClientProfile.objects.filter(user=user).exists():
        r.append("client")
    if ProfessionalProfile.objects.filter(user=user).exists():
        r.append("couturier")
    return " + ".join(r) or "aucun profil"


class Command(BaseCommand):
    help = "Liste et règle les comptes en double (même e-mail, ou client ET couturier)."

    def add_arguments(self, parser):
        parser.add_argument("--appliquer", action="store_true", help="Applique les corrections.")

    def handle(self, *args, **opts):
        appliquer = opts["appliquer"]
        self._emails(appliquer)
        self._double_profil(appliquer)
        if not appliquer:
            self.stdout.write(self.style.WARNING(
                "\nRien n'a été modifié. Relance avec --appliquer pour corriger."))

    # ── 1. Même e-mail ──────────────────────────────────────────
    def _emails(self, appliquer):
        groupes = defaultdict(list)
        for u in User.objects.exclude(email="").annotate(e=Lower("email")):
            groupes[u.e.strip()].append(u)
        doublons = {e: us for e, us in groupes.items() if len(us) > 1}

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n1. E-mails en double : {len(doublons)}"))
        for email, users in doublons.items():
            classes = sorted(
                users,
                key=lambda u: (activite(u), u.is_active, u.last_login.timestamp() if u.last_login else 0),
                reverse=True,
            )
            garde, autres = classes[0], classes[1:]
            self.stdout.write(f"\n  {email}")
            for u in classes:
                marque = "GARDÉ   " if u == garde else "en pause"
                self.stdout.write(
                    f"    [{marque}] #{u.id} {u.username} · {role(u)} · activité {activite(u)} · "
                    f"inscrit le {u.date_joined:%d/%m/%Y} · "
                    f"dernière connexion {u.last_login:%d/%m/%Y}" if u.last_login else
                    f"    [{marque}] #{u.id} {u.username} · {role(u)} · activité {activite(u)} · "
                    f"inscrit le {u.date_joined:%d/%m/%Y} · jamais connecté"
                )
            if appliquer:
                with transaction.atomic():
                    for u in autres:
                        origine = u.email
                        u.email = f"doublon_{u.id}@doublon.invalid"
                        u.is_active = False
                        u.save(update_fields=["email", "is_active"])
                        DepartCompte.objects.create(
                            user=u, action=DepartCompte.DESACTIVATION,
                            precision=f"Doublon de l'e-mail {origine} : compte gardé #{garde.id} ({garde.username}).",
                        )
                    if garde.email != email:
                        garde.email = email  # e-mail remis en minuscules
                        garde.save(update_fields=["email"])

        # E-mails uniques mais avec des majuscules : on les remet en minuscules
        if appliquer:
            for u in User.objects.exclude(email=""):
                propre = u.email.strip().lower()
                if u.email != propre and not User.objects.filter(email=propre).exclude(id=u.id).exists():
                    u.email = propre
                    u.save(update_fields=["email"])

    # ── 2. Client ET couturier ──────────────────────────────────
    def _double_profil(self, appliquer):
        users = User.objects.filter(client_profile__isnull=False, professional_profile__isnull=False)
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n2. Comptes à la fois client ET couturier : {users.count()}"))
        for u in users:
            client, pro = u.client_profile, u.professional_profile
            act_client = (Commande.objects.filter(client_profile=client).count()
                          + MesureClient.objects.filter(client_profile=client).count())
            act_pro = (Commande.objects.filter(professional_profile=pro).count()
                       + ModeleDisponible.objects.filter(professional_profile=pro).count())
            self.stdout.write(f"  #{u.id} {u.email} · activité client {act_client} · activité couturier {act_pro}")
            if act_client and act_pro:
                self.stdout.write(self.style.ERROR(
                    "    -> les deux profils sont utilisés : à traiter à la main (aucune modification)."))
                continue
            vide = pro if act_client or not act_pro else client
            nom = "couturier" if vide is pro else "client"
            self.stdout.write(f"    -> le profil {nom} est vide : {'supprimé' if appliquer else 'sera supprimé'}")
            if appliquer:
                vide.delete()
