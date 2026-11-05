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
    list_display = ('id', 'is_maintenance_mode', 'nb_modeles_gratuits', 'nb_retraits_gratuits', 'nb_commandes_mensuelles_gratuites', 'global_title', 'send_to_all_now')
    list_editable = ('is_maintenance_mode', 'nb_modeles_gratuits', 'nb_retraits_gratuits', 'nb_commandes_mensuelles_gratuites', 'send_to_all_now')  # modifiable directement dans la liste
    fieldsets = (
        ("Couturiers sans abonnement", {"fields": ("nb_modeles_gratuits", "nb_retraits_gratuits", "nb_commandes_mensuelles_gratuites")}),
        ("Comptes supprimés", {"fields": ("delai_recuperation_jours",)}),
        ("Maintenance", {"fields": ("is_maintenance_mode", "maintenance_message")}),
        ("Message à tous les utilisateurs", {
            "fields": ("global_title", "global_message", "destinataires", "send_to_all_now"),
            "description": "Coche « ENVOYER », puis Enregistrer : le message arrive dans l'appli ET sur les téléphones (même appli fermée).",
        }),
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



# ── Suivi, avis, notifications push ─────────────────────────
from core.models import AvisCouturier, PaiementCommande, AppareilPush  # noqa: E402


@admin.register(AvisCouturier)
class AvisCouturierAdmin(admin.ModelAdmin):
    list_display = ('professional_profile', 'note', 'client_profile', 'date', 'visible')
    list_filter = ('visible', 'note')
    list_editable = ('visible',)  # masquer un avis abusif


@admin.register(PaiementCommande)
class PaiementCommandeAdmin(admin.ModelAdmin):
    list_display = ('commande', 'montant', 'moyen', 'date')


@admin.register(AppareilPush)
class AppareilPushAdmin(admin.ModelAdmin):
    list_display = ('user', 'plateforme', 'maj_le')



# ── Messages ciblés (une personne, un groupe, tout le monde) ──
from django.contrib import messages as _msg  # noqa: E402
from core.models import EnvoiMessage  # noqa: E402


@admin.register(EnvoiMessage)
class EnvoiMessageAdmin(admin.ModelAdmin):
    list_display = ('titre', 'cible', 'nb_personnes', 'ville', 'envoye_le', 'resultat')
    list_filter = ('cible',)
    search_fields = ('titre', 'message')
    autocomplete_fields = ('personnes',)
    readonly_fields = ('envoye_le', 'resultat')
    fieldsets = (
        (None, {
            "fields": ("titre", "message", "cible", "personnes", "ville"),
            "description": "Le message arrive dans la liste de l'appli ET sur le téléphone (même appli fermée). "
                           "Il part dès que tu cliques Enregistrer.",
        }),
        ("Envoi", {"fields": ("envoye_le", "resultat")}),
    )

    @admin.display(description="Personnes")
    def nb_personnes(self, obj):
        return obj.personnes.count() if obj.cible == 'PERSONNES' else "—"

    def get_readonly_fields(self, request, obj=None):
        # Un message déjà parti n'est plus modifiable (on garde l'historique exact)
        if obj and obj.envoye_le:
            return ('titre', 'message', 'cible', 'personnes', 'ville', 'envoye_le', 'resultat')
        return self.readonly_fields

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)  # les personnes choisies sont enregistrées ici
        obj = form.instance
        if obj.envoye_le:
            return
        if obj.cible == 'PERSONNES' and not obj.personnes.exists():
            self.message_user(request, "Choisis au moins une personne : le message n'est pas parti.", _msg.WARNING)
            return
        obj.envoyer()
        self.message_user(request, f"Message « {obj.titre} » envoyé.", _msg.SUCCESS)
