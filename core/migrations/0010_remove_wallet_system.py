from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_commande_type_paiement'),
    ]

    operations = [
        # Renomme le champ (préserve les données existantes) au lieu de
        # supprimer + recréer.
        migrations.RenameField(
            model_name='offreabonnement',
            old_name='prix_points',
            new_name='prix',
        ),
        # Le wallet/système de points n'est plus utilisé : le paiement des
        # commandes se fait hors-app (Mobile Money / Espèce), et l'abonnement
        # est géré directement via la table Abonnement, activée depuis le
        # site web (sans passer par un solde de points).
        migrations.RemoveField(
            model_name='transaction',
            name='wallet',
        ),
        migrations.DeleteModel(
            name='Transaction',
        ),
        migrations.DeleteModel(
            name='Wallet',
        ),
    ]
