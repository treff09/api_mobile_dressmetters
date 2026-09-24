"""
Django settings for dressmaker project.
"""

import os
from pathlib import Path
from datetime import timedelta
import ssl
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# 🔥 CHARGEMENT EXPLICITE DU .ENV (À la racine du projet)
load_dotenv(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = 'django-insecure-piqny!!-0u6kcfjy&zaq-f@r9*+g5bpbu#2^3(r&4gq$0vd5jy'

DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '10.0.2.2']

# Application definition

INSTALLED_APPS = [
    'daphne',  # 🚀 Indispensable pour Channels (doit être tout en haut)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'accounts.apps.AccountsConfig',
    'core.apps.CoreConfig',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'mensuration',
    'corsheaders',
    'qr_code',
    'commandes',
    'rechargements',
    'notifications',  # 🔔 Ton app pour le temps réel
    'channels',       # 🔥 Pour gérer les WebSockets
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
     'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}
SPECTACULAR_SETTINGS = {
    'TITLE': 'API Gestion Atelier Couture & Mensurations',
    'DESCRIPTION': 'API backend pour la digitalisation des ateliers de couture. Intègre la logique de verrouillage des mesures par commande.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # Optionnel : pour trier tes endpoints par ordre alphabétique dans l'interface
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
    },
}
CORS_ALLOW_ALL_ORIGINS = True 

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', # Placé en haut pour CORS
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'dressmaker.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# --- CONFIGURATION TEMPS RÉEL (CHANNELS) ---
ASGI_APPLICATION = 'dressmaker.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [('127.0.0.1', 6379)], # Adresse locale de Redis
        },
    },
}

WSGI_APPLICATION = 'dressmaker.wsgi.application'

AUTH_USER_MODEL = 'auth.User'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = 'static/'
MEDIA_URL = '/media/' 
MEDIA_ROOT = BASE_DIR / 'media' 

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- CONFIGURATION EMAIL ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')
# Sécurité : si la variable est vide, on met 465 par défaut
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 465))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')

# Configuration SSL pour port 465
EMAIL_USE_SSL = True
EMAIL_USE_TLS = False
from email.utils import formataddr
# Contexte SSL pour éviter les erreurs de certificat (Hostname mismatch)
EMAIL_SSL_CONTEXT = ssl._create_unverified_context()

# Sécurité pour éviter le None dans le FROM
if EMAIL_HOST_USER:
    DEFAULT_FROM_EMAIL = formataddr(("COUTURIER DIGITAL", EMAIL_HOST_USER))
else:
    DEFAULT_FROM_EMAIL = "COUTURIER DIGITAL <noreply@couturier-digital.com>"
    
REPLY_TO = [DEFAULT_FROM_EMAIL]
PAYMENT_GATEWAY_BASE_URL = os.environ.get("PAYMENT_GATEWAY_BASE_URL", "http://localhost:8000/api/payments")
PAYMENT_GATEWAY_API_KEY = os.environ.get("PAYMENT_GATEWAY_API_KEY", "")
