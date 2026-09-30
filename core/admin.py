from django.contrib import admin
from .models import *
from core.models import *
admin.site.register(ProfessionalProfile)
admin.site.register(ClientProfile)
admin.site.register(TypeVetement)
#admin.site.register(Mesure)
admin.site.register(ModeleDisponible)
admin.site.register(Commande)
admin.site.register(ModeleCommande)
admin.site.register(OffreAbonnement)
admin.site.register(LibelleMesure)
admin.site.register(MesureClient)


@admin.register(Abonnement)
class AbonnementAdmin(admin.ModelAdmin):
    list_display = ('professional_profile', 'offre', 'date_debut', 'date_fin', 'est_actif', 'jours_restants')
    list_filter = ('offre',)
    search_fields = ('professional_profile__nom_entreprise',)

# core/admin.py
# core/admin.py
from django.contrib import admin
from .models import AppConfiguration

@admin.register(AppConfiguration)
class AppConfigurationAdmin(admin.ModelAdmin):
    # Correction ici : on utilise 'global_title' au lieu de 'global_notification_title'
    list_display = ('id', 'is_maintenance_mode', 'nb_modeles_gratuits', 'nb_retraits_gratuits', 'global_title', 'send_to_all_now')
    list_editable = ('is_maintenance_mode', 'nb_modeles_gratuits', 'nb_retraits_gratuits', 'send_to_all_now')  # modifiable directement dans la liste
    fieldsets = (
        ("Couturiers sans abonnement", {"fields": ("nb_modeles_gratuits", "nb_retraits_gratuits")}),
        ("Comptes supprimés", {"fields": ("delai_recuperation_jours",)}),
        ("Maintenance", {"fields": ("is_maintenance_mode", "maintenance_message")}),
        ("Message à tous les utilisateurs", {"fields": ("global_title", "global_message", "send_to_all_now")}),
    )

    # Empêche la création de plusieurs lignes (Singleton)
    def has_add_permission(self, request):
        if AppConfiguration.objects.exists():
            return False
        return True

    # Empêche la suppression de la configuration
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PrivacyPolicy)
class PrivacyPolicyAdmin(admin.ModelAdmin):
    list_display = ('titre', 'derniere_mise_a_jour')
    
    # Empêcher d'en créer plusieurs si tu veux n'en garder qu'une seule
    def has_add_permission(self, request):
        return not PrivacyPolicy.objects.exists()
    
@admin.register(ConditionGenerale)
class ConditionGeneraleAdmin(admin.ModelAdmin):
    list_display = ('titre', 'derniere_mise_a_jour')
    
    # Empêcher d'en créer plusieurs si tu veux n'en garder qu'une seule
    def has_add_permission(self, request):
        return not ConditionGenerale.objects.exists()

# ── Départs des utilisateurs ─────────────────────────────────
from django.utils import timezone as _tz
from .models import MotifDepart, DepartCompte


@admin.register(MotifDepart)
class MotifDepartAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'demande_precision', 'ordre', 'actif')
    list_editable = ('demande_precision', 'ordre', 'actif')


@admin.register(DepartCompte)
class DepartCompteAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'motif', 'precision', 'date_demande', 'statut')
    list_filter = ('action', 'motif')
    search_fields = ('user__email', 'user__username', 'precision')
    readonly_fields = ('user', 'action', 'motif', 'precision', 'date_demande', 'date_reactivation', 'date_effacement')
    actions = ['reactiver']

    @admin.display(description="Statut")
    def statut(self, obj):
        if obj.date_effacement:
            return "Données effacées"
        if obj.date_reactivation:
            return f"Réactivé le {obj.date_reactivation:%d/%m/%Y}"
        return "En cours"

    @admin.action(description="Réactiver les comptes sélectionnés")
    def reactiver(self, request, queryset):
        n = 0
        for d in queryset.filter(date_reactivation__isnull=True, date_effacement__isnull=True):
            d.user.is_active = True
            d.user.save(update_fields=['is_active'])
            d.date_reactivation = _tz.now()
            d.save(update_fields=['date_reactivation'])
            n += 1
        self.message_user(request, f"{n} compte(s) réactivé(s).")

