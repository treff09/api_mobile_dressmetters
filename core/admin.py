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
    list_display = ('id', 'is_maintenance_mode', 'global_title', 'send_to_all_now')
    list_editable = ('is_maintenance_mode', 'send_to_all_now') # Optionnel : permet de cocher directement dans la liste

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
    