"""
Verrou en base : une adresse e-mail ne peut appartenir qu'à UN seul compte
(sans tenir compte des majuscules). Les e-mails vides ne sont pas concernés.

S'il reste des doublons, la migration s'arrête avec un message : lancer d'abord
    python manage.py doublons_comptes --appliquer
"""
from django.db import migrations

CREER = "CREATE UNIQUE INDEX IF NOT EXISTS auth_user_email_unique_ci ON auth_user (LOWER(email)) WHERE email <> ''"
SUPPRIMER = "DROP INDEX IF EXISTS auth_user_email_unique_ci"


def creer_index(apps, schema_editor):
    with schema_editor.connection.cursor() as c:
        c.execute("SELECT LOWER(email), COUNT(*) FROM auth_user WHERE email <> '' GROUP BY LOWER(email) HAVING COUNT(*) > 1")
        doublons = c.fetchall()
    if doublons:
        liste = ", ".join(f"{e} ({n} comptes)" for e, n in doublons[:10])
        raise RuntimeError(
            f"\n\n{len(doublons)} e-mail(s) utilisé(s) par plusieurs comptes : {liste}\n"
            "Lance d'abord :  python manage.py doublons_comptes            (pour voir)\n"
            "puis           :  python manage.py doublons_comptes --appliquer\n"
            "et relance    :  python manage.py migrate\n"
        )
    schema_editor.execute(CREER)


def supprimer_index(apps, schema_editor):
    schema_editor.execute(SUPPRIMER)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core", "0023_delai_recuperation"),
    ]
    operations = [migrations.RunPython(creer_index, supprimer_index)]
