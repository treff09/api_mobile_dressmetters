from django.contrib import admin
from django.urls import path, include
from django.conf import settings # Importez settings
from django.conf.urls.static import static 
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,)
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from commandes.views import landing_page_view
urlpatterns = [
    # Site vitrine (page d'accueil publique)
    path('', landing_page_view, name='landing'),
    # Chemin pour le panneau d'administration de Django
    path('admin/', admin.site.urls),
    # --- DOCUMENTATION SWAGGER AUTOMATIQUE ---
    # Télécharge le fichier de schéma brut (JSON/YAML)
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    # Affiche l'interface graphique interactive Swagger UI
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # Inclusion des URL de l'application accounts sous le chemin 'api/v1/accounts/'
    path('api/v1/accounts/', include('accounts.urls')),
    path('api/v1/mensuration/', include('mensuration.urls')),
    path('api/v1/qrcode/', include('qr_code.urls')),
    # Inclusion des URL de l'application core sous le chemin 'api/v1/core/'
    path('api/v1/core/', include('core.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/commandes/', include('commandes.urls')),
    path('api/v1/subscription/', include('rechargements.api_urls')),
    path('', include('rechargements.urls')),
    path('api/v1/notifications/', include('notifications.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)