"""
Offre d'ouverture : chaque couturier qui crée son compte pendant la période
choisie dans l'admin (Configuration > Offre d'ouverture) reçoit un mois de
Premium offert, une seule fois.

C'est un cadeau : aucun paiement n'est créé, et l'achat du Premium reste sur
le site web, inchangé. Si le couturier est déjà abonné, les jours s'ajoutent.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone


def offrir_mois_ouverture(pro, prevenir=True):
    from core.models import Abonnement, AppConfiguration, ProfessionalProfile
    offre = AppConfiguration.offre_ouverture()
    if offre is None:
        return False
    debut, fin, jours = offre
    cree_le = timezone.localdate(pro.user.date_joined) if pro.user.date_joined else timezone.localdate()
    if not (debut <= cree_le <= fin):
        return False
    with transaction.atomic():
        p = ProfessionalProfile.objects.select_for_update().get(pk=pro.pk)
        if p.offre_ouverture_recue:
            return False
        now = timezone.now()
        abo = Abonnement.objects.select_for_update().filter(professional_profile=p).first()
        if abo is None:
            Abonnement.objects.create(professional_profile=p, date_fin=now + timedelta(days=jours))
        else:
            depart = abo.date_fin if abo.date_fin and abo.date_fin > now else now
            abo.date_fin = depart + timedelta(days=jours)
            abo.save(update_fields=['date_fin'])
        p.offre_ouverture_recue = True
        p.save(update_fields=['offre_ouverture_recue'])
    if prevenir:
        try:
            from core.push import notifier
            notifier(p.user, "Bienvenue ! Premium offert 🎁",
                     f"Pour l'ouverture de votre compte, profitez de {jours} jours de Premium gratuits : "
                     f"modèles et commandes illimités.")
        except Exception:  # noqa: BLE001  (la notification ne doit jamais bloquer)
            pass
    return True
