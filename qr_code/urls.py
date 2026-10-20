from django.urls import path, include

from .views import GenerateQRView, QRAccessView, LienPartageView

urlpatterns = [
    # ... autres routes ...
    
    # Route pour générer le QR code (pour les couturiers)
    path('lien-partage/', LienPartageView.as_view(), name='qr-lien-partage'),
    path('generate/', GenerateQRView.as_view(), name='generate-qr'),
    
    # Route pour accéder via le QR code (pour les clients)
    path('access/<str:token_key>/', QRAccessView.as_view(), name='qr-access'),
]