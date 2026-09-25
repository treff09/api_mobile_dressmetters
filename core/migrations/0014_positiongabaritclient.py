# Migration : ajout du modèle PositionGabaritClient
# Stocke la position personnalisée des points du gabarit par client

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_alter_modelecommande_image_tissu'),
    ]

    operations = [
        migrations.CreateModel(
            name='PositionGabaritClient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position_x', models.FloatField(default=0.0)),
                ('position_y', models.FloatField(default=0.0)),
                ('client_profile', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='positions_gabarit',
                    to='core.clientprofile',
                )),
                ('libelle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='positions_clients',
                    to='core.libellemesure',
                )),
            ],
            options={
                'verbose_name': 'Position gabarit client',
                'verbose_name_plural': 'Positions gabarit clients',
                'unique_together': {('client_profile', 'libelle')},
            },
        ),
    ]
