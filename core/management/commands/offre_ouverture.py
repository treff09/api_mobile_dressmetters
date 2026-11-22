"""
Donne l'offre d'ouverture aux couturiers DÉJÀ inscrits pendant la période
(ex. inscrits depuis le 1er novembre, avant la mise en ligne de l'offre).

    python manage.py offre_ouverture            # applique
    python manage.py offre_ouverture --essai    # montre seulement qui la recevrait
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import AppConfiguration, ProfessionalProfile
from core.offre_ouverture import offrir_mois_ouverture


class Command(BaseCommand):
    help = "Applique l'offre d'ouverture (Premium offert) aux couturiers inscrits pendant la période."

    def add_arguments(self, parser):
        parser.add_argument('--essai', action='store_true', help="N'applique rien, affiche seulement la liste.")

    def handle(self, *args, **opts):
        offre = AppConfiguration.offre_ouverture()
        if offre is None:
            self.stdout.write("Offre d'ouverture désactivée dans l'admin : rien à faire.")
            return
        debut, fin, jours = offre
        self.stdout.write(f"Période : du {debut:%d/%m/%Y} au {fin:%d/%m/%Y} · {jours} jours offerts")
        nb = 0
        for pro in ProfessionalProfile.objects.select_related('user').filter(offre_ouverture_recue=False):
            cree = timezone.localdate(pro.user.date_joined)
            if not (debut <= cree <= fin) or not pro.user.is_active:
                continue
            if opts['essai']:
                self.stdout.write(f"  · {pro.nom_entreprise} (inscrit le {cree:%d/%m/%Y})")
                nb += 1
            elif offrir_mois_ouverture(pro):
                self.stdout.write(f"  ✓ {pro.nom_entreprise} (inscrit le {cree:%d/%m/%Y})")
                nb += 1
        self.stdout.write(self.style.SUCCESS(
            f"{nb} couturier(s) {'concerné(s)' if opts['essai'] else 'ont reçu leur mois offert'}."))
