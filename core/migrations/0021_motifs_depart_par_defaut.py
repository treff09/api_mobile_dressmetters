from django.db import migrations

MOTIFS = [
    ("Je n'utilise plus l'application", False),
    ("L'application est trop compliquée", False),
    ("J'ai trouvé une autre solution", False),
    ("J'ai eu un problème avec une commande", False),
    ("Je reçois trop de notifications", False),
    ("Je m'inquiète pour mes données", False),
    ("Autre", True),
]


def charger(apps, schema_editor):
    MotifDepart = apps.get_model("core", "MotifDepart")
    if MotifDepart.objects.exists():
        return
    for i, (libelle, precision) in enumerate(MOTIFS):
        MotifDepart.objects.create(libelle=libelle, demande_precision=precision, ordre=i)


class Migration(migrations.Migration):
    dependencies = [("core", "0020_depart_compte_et_retrait_modele")]
    operations = [migrations.RunPython(charger, migrations.RunPython.noop)]
