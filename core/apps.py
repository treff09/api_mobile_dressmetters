from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from core import signals_push  # noqa: F401  (notifications → téléphone)
        from core import signals_offre  # noqa: F401  (offre d'ouverture : Premium offert)
