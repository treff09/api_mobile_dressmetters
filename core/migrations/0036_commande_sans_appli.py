from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0035_moderation')]
    operations = [
        migrations.AddField('clientprofile', 'invite', models.BooleanField(default=False)),
        migrations.AddField('commande', 'lien_suivi', models.CharField(blank=True, max_length=32, null=True, unique=True)),
        migrations.AddField('commande', 'creee_par_couturier', models.BooleanField(default=False)),
        migrations.AddField('commande', 'description', models.CharField(blank=True, default='', max_length=255)),
    ]
