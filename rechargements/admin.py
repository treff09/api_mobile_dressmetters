from django.contrib import admin, messages

from .models import PaiementChariow, PulseChariow
from .tasks import prolonger_abonnement


@admin.register(PaiementChariow)
class PaiementChariowAdmin(admin.ModelAdmin):
    list_display = ("reference", "professional_profile", "offre", "montant_attendu", "montant_paye", "statut",
                    "applique", "abonnement_jusquau", "cree_le")
    list_filter = ("statut", "applique", "offre")
    search_fields = ("reference", "sale_id", "transaction_id", "professional_profile__nom_entreprise",
                     "professional_profile__user__email")
    readonly_fields = [f.name for f in PaiementChariow._meta.fields]
    actions = ["valider_anomalie"]

    @admin.action(description="Valider (prolonger l'abonnement) — anomalies vérifiées uniquement")
    def valider_anomalie(self, request, queryset):
        from django.db import transaction
        n = 0
        for p in queryset.filter(statut="ANOMALIE", applique=False):
            with transaction.atomic():
                p.abonnement_jusquau = prolonger_abonnement(p)
                p.statut = "PAYE"; p.applique = True
                p.note += f"\nValidé manuellement par {request.user}"
                p.save()
            n += 1
        messages.info(request, f"{n} paiement(s) validé(s).")

    def has_add_permission(self, request):
        return False


@admin.register(PulseChariow)
class PulseChariowAdmin(admin.ModelAdmin):
    list_display = ("delivery_id", "evenement", "recu_le", "traite", "erreur")
    list_filter = ("evenement", "traite")
    search_fields = ("delivery_id",)
    readonly_fields = [f.name for f in PulseChariow._meta.fields]

    def has_add_permission(self, request):
        return False
