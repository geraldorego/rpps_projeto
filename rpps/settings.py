import os
import logging
from django.contrib.messages import constants
from decouple import config, Csv

# Caminhos base
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# =====================================================================
# Segurança básica
# =====================================================================

SECRET_KEY = config(
    'SECRET_KEY',
    default='awh8r7f_)vmkdh-djpwg7_ywn3#7=_x%%(2_wtj9_-qyp%fk)r'
)

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='127.0.0.1,localhost',
    cast=Csv()
)

# Configurações de segurança e CSRF por ambiente
if not DEBUG:
    # Produção
    SECURE_SSL_REDIRECT = False  # ajuste para True se for forçar HTTPS atrás do Nginx
    SESSION_COOKIE_SECURE = False  # True se somente HTTPS
    SECURE_PROXY_SSL_HEADER = None  # ou ('HTTP_X_FORWARDED_PROTO', 'https') se Nginx repassar
    CSRF_COOKIE_SECURE = False  # True se somente HTTPS
    CSRF_COOKIE_SAMESITE = 'Lax'

    # Origens confiáveis para CSRF em produção
    CSRF_TRUSTED_ORIGINS = [
        'https://rpps.alprevidencia.gov.br',
    ]
else:
    # Desenvolvimento
    SECURE_SSL_REDIRECT = False
    SECURE_PROXY_SSL_HEADER = None
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    CSRF_COOKIE_SAMESITE = 'Lax'

    # Origens confiáveis para CSRF em desenvolvimento (via .env)
    CSRF_TRUSTED_ORIGINS = config(
        'CSRF_ORIGINS',
        default='http://127.0.0.1:8000,http://localhost:8000',
        cast=Csv()
    )

# HSTS (comentei para evitar problemas enquanto ajusta HTTPS)
# SECURE_HSTS_SECONDS = 31536000  # 1 ano
# SECURE_HSTS_PRELOAD = True
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True

SECURE_CONTENT_TYPE_NOSNIFF = True

# =====================================================================
# Logging
# =====================================================================

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'django.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'app_rpps': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# =====================================================================
# Apps / Middleware
# =====================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'app_rpps',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'rpps.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'app_rpps/templates/app_rpps')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'rpps.wsgi.application'

# =====================================================================
# Banco de dados
# =====================================================================

DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': config('DB_NAME', default='rpps'),
        'USER': config('DB_USER', default='sa'),
        'PASSWORD': config('DB_PASSWORD', default='geraldorego'),
        'HOST': config('DB_HOST', default='ALPREVSQLSERVER\\ALPREVSQLSERVER'),
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'extra_params': (
                f"Server={config('DB_HOST_IP', default='10.1.63.115\\ALPREVSQLSERVER')};"
                "TrustServerCertificate=yes"
            ),
        },
    },
}

# =====================================================================
# Autenticação / Senhas
# =====================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# =====================================================================
# Internacionalização
# =====================================================================

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# =====================================================================
# Arquivos estáticos e mídias
# =====================================================================

STATIC_URL = '/static/'

# Para desenvolvimento (onde você tem app_rpps/static)
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'app_rpps/static')]

# Para produção (coletados com collectstatic)
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/midia/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'app_rpps/midia')

# Whitenoise
# Em produção você pode usar a storage com manifest:
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# No momento, está usando a storage padrão:
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# =====================================================================
# Login / Mensagens
# =====================================================================

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'menu'

MESSAGE_TAGS = {
    constants.DEBUG: 'alert-primary',
    constants.ERROR: 'alert-danger',
    constants.WARNING: 'alert-warning',
    constants.SUCCESS: 'alert-success',
    constants.INFO: 'alert-info',
}
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

# =====================================================================
# CSRF / CORS / HTMX
# =====================================================================

# Header customizado (HTMX etc.)
CSRF_HEADER_NAME = 'HTTP_HX_REQUEST'

# Cookie CSRF
CSRF_COOKIE_HTTPONLY = False  # se quiser bloquear acesso JS, mude para True
# CSRF_COOKIE_SAMESITE já foi definido no bloco condicional (Lax)

# Expor cabeçalhos
CORS_EXPOSE_HEADERS = ['Content-Type']