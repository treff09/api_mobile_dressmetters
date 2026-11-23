from django.db import migrations


def corriger(apps, schema_editor):
    """Commandes déjà saisies par un couturier : paiement convenu renseigné (acompte ou total)."""
    Commande = apps.get_model('core', 'Commande')
    for c in Commande.objects.filter(creee_par_couturier=True, type_paiement__isnull=True):
        c.type_paiement = 'ACOMPTE' if 0 < (c.acompte_demande or 0) < (c.total_commande or 0) else 'TOTAL'
        c.save(update_fields=['type_paiement'])


class Migration(migrations.Migration):
    dependencies = [('core', '0037_offre_ouverture')]
    operations = [migrations.RunPython(corriger, migrations.RunPython.noop)]
