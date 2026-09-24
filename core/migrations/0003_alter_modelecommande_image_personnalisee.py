# Migration corrigée : upload_to_uuid renommé en upload_modele_personnalise

import core.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_modelecommande_image_personnalisee_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='modelecommande',
            name='image_personnalisee',
            field=models.ImageField(blank=True, null=True, upload_to=core.models.upload_modele_personnalise),
        ),
    ]
