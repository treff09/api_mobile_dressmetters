"""
QR code de DÉMONSTRATION pour l'examen Google Play : il n'expire pas et sert
autant de fois qu'on veut. Il ouvre le catalogue du couturier de test.

    python manage.py qr_demo
    python manage.py qr_demo --email autre.couturier@...    # autre couturier
    python manage.py qr_demo --supprimer                    # désactive le QR de démo

Crée l'image media/qr_demo/qr_demo.png (lien affiché à la fin) et affiche le code
à saisir à la main dans l'app (« Pas de caméra ? Saisis le code »).
"""
import io

import qrcode
import shortuuid
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import ProfessionalProfile, QRToken

SITE = "https://dressmetter.stephaneboundaone.tech"


class Command(BaseCommand):
    help = "Crée le QR code permanent de démonstration (couturier de test)."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="test.couturier@treffcommunication.tech")
        parser.add_argument("--site", default=SITE)
        parser.add_argument("--supprimer", action="store_true")

    def handle(self, *args, **o):
        pro = ProfessionalProfile.objects.filter(user__email__iexact=o["email"]).first()
        if not pro:
            raise CommandError(f"Aucun couturier avec l'e-mail {o['email']}. "
                               "Lance d'abord : python manage.py creer_comptes_test")
        if o["supprimer"]:
            n, _ = QRToken.objects.filter(professional_profile=pro, permanent=True).delete()
            self.stdout.write(self.style.SUCCESS(f"{n} QR de démonstration supprimé(s)."))
            return

        qr = QRToken.objects.filter(professional_profile=pro, permanent=True).first()
        if not qr:
            qr = QRToken.objects.create(professional_profile=pro, token=shortuuid.uuid(), permanent=True)

        # Même contenu que les QR générés par l'app
        url = f"{o['site'].rstrip('/')}/api/v1/qrcode/access/{qr.token}/"
        dossier = settings.MEDIA_ROOT if isinstance(settings.MEDIA_ROOT, str) else str(settings.MEDIA_ROOT)
        import os
        os.makedirs(os.path.join(dossier, "qr_demo"), exist_ok=True)
        chemin = os.path.join(dossier, "qr_demo", "qr_demo.png")
        img = qrcode.make(url, box_size=12, border=4)
        img.save(chemin)

        self.stdout.write(self.style.SUCCESS("\nQR code de démonstration prêt (n'expire pas) :"))
        self.stdout.write(f"  Couturier : {pro.nom_entreprise}")
        self.stdout.write(f"  Image     : {o['site'].rstrip('/')}{settings.MEDIA_URL}qr_demo/qr_demo.png")
        self.stdout.write(f"  Code      : {qr.token}   (à saisir dans l'app si pas de caméra)")
