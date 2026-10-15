"""Configuración de GENEOS Web Admin.

Todo lo que cambia entre la computadora local y un servidor se toma de variables de entorno (archivo .env opcional).
Por defecto funciona localmente con SQLite; con DB_NAME usa PostgreSQL.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env():
    f = BASE_DIR / ".env"
    if f.exists():
        for linea in f.read_text().splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_cargar_env()
env = os.environ.get

DEBUG = env("DEBUG", "1") == "1"
SECRET_KEY = env("SECRET_KEY", "solo-para-desarrollo-local-cambiar-en-servidor")
if not DEBUG and SECRET_KEY.startswith("solo-para"):
    raise RuntimeError("Definí SECRET_KEY en el servidor.")
ALLOWED_HOSTS = [h for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "sitios", "contenidos", "editorial", "publicacion", "formularios",
    "wagtail.contrib.forms", "wagtail.contrib.redirects", "wagtail.contrib.table_block", "wagtail.contrib.settings",
    "wagtail.embeds", "wagtail.sites", "wagtail.users", "wagtail.snippets", "wagtail.documents", "wagtail.images",
    "wagtail.search", "wagtail.admin", "wagtail", "modelcluster", "taggit", "django_filters",
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
                                       "django.contrib.messages.context_processors.messages"]},
}]
WSGI_APPLICATION = "config.wsgi.application"

if env("DB_NAME"):
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": env("DB_NAME"), "USER": env("DB_USER", ""),
                             "PASSWORD": env("DB_PASSWORD", ""), "HOST": env("DB_HOST", "localhost"), "PORT": env("DB_PORT", "5432")}}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "var" / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
                            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
                            {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "es"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "var" / "static"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "var" / "media")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

# Sesiones y seguridad
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "SAMEORIGIN"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Email: en local se muestra en la terminal. En el servidor: EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD.
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST, EMAIL_PORT = env("EMAIL_HOST"), int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER, EMAIL_HOST_PASSWORD = env("EMAIL_HOST_USER", ""), env("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env("EMAIL_USE_TLS", "1") == "1"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "GENEOS Web Admin <no-responder@geneos.com.ar>")

# Wagtail
WAGTAIL_SITE_NAME = "GENEOS Web Admin"
WAGTAILADMIN_BASE_URL = env("GWA_URL_PUBLICA", "http://localhost:8000")
WAGTAIL_I18N_ENABLED = False
WAGTAILIMAGES_EXTENSIONS = ["gif", "jpg", "jpeg", "png", "webp", "avif", "svg"]
WAGTAILDOCS_EXTENSIONS = ["pdf", "zip", "docx", "xlsx", "pptx", "svg", "png", "jpg"]
WAGTAILADMIN_RICH_TEXT_EDITORS = {"default": {"WIDGET": "wagtail.admin.rich_text.DraftailRichTextArea", "OPTIONS": {"features": ["bold", "italic", "link", "ol", "ul"]}}}
WAGTAIL_ENABLE_UPDATE_CHECK = False
WAGTAILADMIN_COMMENTS_ENABLED = True

# Motor de sitios y publicación
GWA_RENDERER_DIR = BASE_DIR / "renderer"
GENEOS_WEB_DIR = BASE_DIR / Path(env("GENEOS_WEB_DIR", str(BASE_DIR.parent / "GENEOS WEB")))  # relativa al repositorio o absoluta
GEAGRO_SRC_DIR = Path(env("GEAGRO_SRC_DIR", str(Path.home() / "Documents/geagro_clean/GEAGRO Geneos : Imagen de marca/GEAGRO WEB 2026")))
GWA_VAR_DIR = BASE_DIR / "var"
GWA_URL_PUBLICA = env("GWA_URL_PUBLICA", "http://localhost:8000")

# Formularios de demo
GWA_CORS_EXTRA = [o for o in env("GWA_CORS_EXTRA", "http://localhost:8000,http://localhost:8102,http://localhost:8103,http://localhost:8104").split(",") if o]
GWA_FORM_SEGUNDOS_MINIMOS = int(env("GWA_FORM_SEGUNDOS_MINIMOS", "3"))
GWA_FORM_MAX_POR_HORA = int(env("GWA_FORM_MAX_POR_HORA", "5"))

(BASE_DIR / "var").mkdir(exist_ok=True)
WAGTAIL_GRAVATAR_PROVIDER_URL = None
