# Les mesures déjà enregistrées deviennent celles de « Moi ».
from django.db import migrations


def rattacher(apps, schema_editor):
    ClientProfile = apps.get_model("core", "ClientProfile")
    PersonneMesuree = apps.get_model("core", "PersonneMesuree")
    MesureClient = apps.get_model("core", "MesureClient")
    for client in ClientProfile.objects.all():
        g = str(client.genre or "").strip().lower()
        moi, _ = PersonneMesuree.objects.get_or_create(
            client_profile=client, est_moi=True,
            defaults={"prenom": "Moi", "genre": "H" if g in ("h", "homme", "m", "masculin") else "F"},
        )
        MesureClient.objects.filter(client_profile=client, personne__isnull=True).update(personne=moi)


class Migration(migrations.Migration):
    dependencies = [("core", "0017_personnes_mesurees")]
    operations = [migrations.RunPython(rattacher, migrations.RunPython.noop)]
