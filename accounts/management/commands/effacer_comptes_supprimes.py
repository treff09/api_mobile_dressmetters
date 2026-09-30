"""
Efface les données personnelles des comptes SUPPRIMÉS depuis plus longtemps que
le délai réglé dans l'admin (30 jours par défaut)
(comme promis dans la politique de confidentialité). Les commandes restent, anonymisées,
pour la comptabilité. Les comptes simplement « désactivés » ne sont jamais touchés.

    python manage.py effacer_comptes_supprimes           # effectue l'effacement
    python manage.py effacer_comptes_supprimes --essai   # montre seulement ce qui serait effacé

En production, elle est lancée automatiquement chaque nuit par Celery Beat
(tâche accounts.tasks.effacer_comptes_supprimes). On peut aussi la lancer à la main.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (DepartCompte, MesureClient, PersonneMesuree, PositionGabaritClient,
                         ModeleDisponible)


class Command(BaseCommand):
    help = "Efface les données personnelles des comptes supprimés depuis plus de 30 jours."

    def add_arguments(self, parser):
        parser.add_argument("--essai", action="store_true", help="N'efface rien, affiche seulement.")

    def handle(self, *args, **opts):
        from core.models import AppConfiguration
        limite = timezone.now() - timezone.timedelta(days=AppConfiguration.delai_recuperation())
        departs = DepartCompte.objects.filter(
            action=DepartCompte.SUPPRESSION, date_demande__lte=limite,
            date_reactivation__isnull=True, date_effacement__isnull=True,
        ).select_related("user")
        n = 0
        for d in departs:
            u = d.user
            self.stdout.write(f"- {u.email or u.username} (supprimé le {d.date_demande:%d/%m/%Y})")
            if opts["essai"]:
                continue
            with transaction.atomic():
                client = getattr(u, "client_profile", None)
                pro = getattr(u, "professional_profile", None)
                if client:
                    MesureClient.objects.filter(client_profile=client).delete()
                    PersonneMesuree.objects.filter(client_profile=client).delete()
                    PositionGabaritClient.objects.filter(client_profile=client).delete()
                    client.nom, client.prenom = "Client", "supprimé"
                    if hasattr(client, "numero_telephone"):
                        client.numero_telephone = None
                    client.save()
                if pro:
                    pro.nom_entreprise = "Atelier supprimé"
                    pro.nom, pro.prenom = "", ""
                    pro.numero_telephone = f"supprime-{pro.id}"  # champ unique
                    pro.save()
                    ModeleDisponible.objects.filter(professional_profile=pro).update(actif=False)
                u.username = f"supprime_{u.id}"
                u.email = f"supprime_{u.id}@supprime.invalid"
                u.first_name = u.last_name = ""
                u.set_unusable_password()
                u.is_active = False
                u.save()
                d.date_effacement = timezone.now()
                d.save(update_fields=["date_effacement"])
            n += 1
        if opts["essai"]:
            self.stdout.write(self.style.WARNING("Mode essai : rien n'a été effacé."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{n} compte(s) effacé(s)."))
