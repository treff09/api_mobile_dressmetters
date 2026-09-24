from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from core.views import UserProfileTypeView
from commandes.views import web_login_view, web_recharge_view
from .views import (
    ChangePasswordView,
    ClientRegistrationView,
    LogoutView,
    PersonalInfoView,
    ProfessionalRegistrationView,
    LoginView,
    ForgotPasswordView , # Importation de la nouvelle vue
    
)

urlpatterns = [
    
    # Inscription
    path('register/client/', ClientRegistrationView.as_view(), name='register_client'),
    path('register/professional/', ProfessionalRegistrationView.as_view(), name='register_professional'),
    
    # Connexion et Token
    path('login/', LoginView.as_view(), name='login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    
    # Récupération de mot de passe (Logique en 3 étapes : Email -> OTP -> Reset)
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    
    # Profil et paramètres
    path('profile-type/', UserProfileTypeView.as_view(), name='user-profile-type'),
    path('personal-info/', PersonalInfoView.as_view(), name='personal-info'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),

    path('accounts/web-login/', web_login_view, name='web_login'),
    path('payments/recharge/', web_recharge_view, name='web_recharge'),

]