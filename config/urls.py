from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import RedirectView
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from formularios import views as formularios
from publicacion import descargas
from publicacion import views as publicacion

urlpatterns = [
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("api/formularios/demo/", formularios.recibir, name="gwa_form_demo"),
    path("api/formularios/demo/token/", formularios.token, name="gwa_form_token"),
    path("descargas/<slug:sitio>/<slug:clave>/", descargas.descargar, name="gwa_descarga"),
    path("vista-previa/<path:ruta>", publicacion.archivo_previa, name="gwa_archivo_previa"),
    path("version/<int:pk>/", publicacion.archivo_preparacion, {"ruta": ""}, name="gwa_version"),
    path("version/<int:pk>/<path:ruta>", publicacion.archivo_preparacion, name="gwa_version_ruta"),
    path("web-local/<slug:clave>/", publicacion.archivo_publico, {"ruta": ""}, name="gwa_web_local"),
    path("web-local/<slug:clave>/<path:ruta>", publicacion.archivo_publico, name="gwa_web_local_ruta"),
    path("admin/", include(wagtailadmin_urls)),
    path("documentos/", include(wagtaildocs_urls)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
