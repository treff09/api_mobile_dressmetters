"""
Teste l'envoi d'e-mail avec la configuration réelle du serveur et affiche
l'erreur EXACTE s'il y en a une.

    python manage.py tester_email ton.adresse@gmail.com
    (Docker)  docker compose exec web python manage.py tester_email ton.adresse@gmail.com
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from accounts.views import send_stylized_otp_email


class Command(BaseCommand):
    help = "Envoie un e-mail de test (code 123456) et affiche l'erreur précise en cas d'échec."

    def add_arguments(self, parser):
        parser.add_argument("destinataire")

    def handle(self, *args, **opts):
        self.stdout.write("Configuration utilisée :")
        for k in ("EMAIL_HOST", "EMAIL_PORT", "EMAIL_USE_SSL", "EMAIL_USE_TLS", "EMAIL_HOST_USER", "EMAIL_TIMEOUT"):
            self.stdout.write(f"  {k} = {getattr(settings, k, None)!r}")
        self.stdout.write(f"  EMAIL_HOST_PASSWORD = {'(défini)' if settings.EMAIL_HOST_PASSWORD else '(VIDE !)'}")
        if not settings.EMAIL_HOST or not settings.EMAIL_HOST_USER:
            self.stdout.write(self.style.ERROR("EMAIL_HOST ou EMAIL_HOST_USER est vide : vérifie le fichier .env"))
            return
        try:
            send_stylized_otp_email(opts["destinataire"], "123456")
            self.stdout.write(self.style.SUCCESS(f"E-mail envoyé à {opts['destinataire']} ✓"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"ÉCHEC : {type(e).__name__} : {e}"))
