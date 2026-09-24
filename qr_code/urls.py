from django.urls import path, include

from .views import GenerateQRView, QRAccessView 

urlpatterns = [
    # ... autres routes ...
    
    # Route pour générer le QR code (pour les couturiers)
    path('generate/', GenerateQRView.as_view(), name='generate-qr'),
    
    # Route pour accéder via le QR code (pour les clients)
    path('access/<str:token_key>/', QRAccessView.as_view(), name='qr-access'),
]