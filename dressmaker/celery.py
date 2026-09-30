"""
Celery : tâches en arrière-plan et tâches planifiées.

Lancer (en plus du serveur web) :
    celery -A dressmaker worker -l info      # exécute les tâches
    celery -A dressmaker beat -l info        # déclenche les tâches planifiées
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dressmaker.settings")

app = Celery("dressmaker")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
