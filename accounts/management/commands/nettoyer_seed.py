"""
Supprime les FAUSSES données créées par « seed_commandes » :
  • les clients  client_seed_001, client_seed_002…  (e-mails …@seed.ci)
  • le couturier pro_seed  (s'il a été créé)
  • toutes leurs commandes, mesures et notifications (suppression en cascade)

Les comptes d'examen Google Play (test.client@ / test.couturier@treffcommunication.tech)
sont GARDÉS : Google en a besoin pour examiner chaque mise à jour.

    python manage.py nettoyer_seed               # montre ce qui serait supprimé (rien n'est effacé)
    python manage.py nettoyer_seed --confirmer   # supprime vraiment
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from core.models import Commande

COMPTES_EXAMEN = {"test.client@treffcommunication.tech", "test.couturier@treffcommunication.tech"}


class Command(BaseCommand):
    help = "Supprime les comptes et commandes fictifs créés par seed_commandes."

    def add_arguments(self, parser):
        parser.add_argument("--confirmer", action="store_true", help="Supprime vraiment (sinon simple aperçu).")

    def handle(self, *args, **o):
        faux = (User.objects
                .filter(Q(username__startswith="client_seed_") | Q(username="pro_seed")
                        | Q(email__iendswith="@seed.ci") | Q(email__iexact="pro_seed@couturier.ci"))
                .exclude(email__in=COMPTES_EXAMEN)
                .exclude(is_superuser=True))
        commandes = Commande.objects.filter(
            Q(client_profile__user__in=faux) | Q(professional_profile__user__in=faux))

        self.stdout.write(f"Comptes fictifs : {faux.count()}")
        for u in faux[:10]:
            self.stdout.write(f"   - {u.username}  {u.email}")
        if faux.count() > 10:
            self.stdout.write(f"   … et {faux.count() - 10} autres")
        self.stdout.write(f"Commandes fictives : {commandes.count()}")
        self.stdout.write(f"Comptes d'examen Google gardés : {', '.join(sorted(COMPTES_EXAMEN))}")

        if not o["confirmer"]:
            self.stdout.write(self.style.WARNING(
                "\nAperçu seulement : rien n'a été supprimé. Relance avec --confirmer pour supprimer."))
            return

        with transaction.atomic():
            n_cmd, _ = commandes.delete()
            n_users, _ = faux.delete()
        self.stdout.write(self.style.SUCCESS(f"Supprimé : {n_cmd} objets liés aux commandes, {n_users} objets liés aux comptes."))
