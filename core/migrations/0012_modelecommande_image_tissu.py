# Migration : ajout du champ image_tissu sur ModeleCommande
# Stocke la photo du tissu fourni par le client → media/commandes/tissu/

import core.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_abonnementpaiement'),
    ]

    operations = [
        migrations.AddField(
            model_name='modelecommande',
            name='image_tissu',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=core.models.upload_tissu_client,
                verbose_name='Photo du tissu client',
            ),
        ),
    ]
