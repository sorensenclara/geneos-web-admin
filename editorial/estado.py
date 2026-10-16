"""Estado editorial (borrador → revisión → aprobado) separado del estado real en cada web (publicado o no)."""
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import ConfigBlog


def ultimo_despliegue(sitio):
    return sitio.despliegues.filter(estado="ok").exclude(tipo="vista_previa").first()


def estado_blog(sitio, ultimo_ok=None):
    """(clave, texto, detalle): desactivado · configurado · aprobado · publicado."""
    ultimo_ok = ultimo_ok if ultimo_ok is not None else ultimo_despliegue(sitio)
    c = ConfigBlog.objects.filter(sitio=sitio).first()
    if c is None:
        return "desactivado", "Desactivado", "Todavía no se configuró. Podés escribir borradores igual."
    borrador = c.get_latest_revision_as_object() if c.has_unpublished_changes and c.latest_revision_id else c
    if not c.live or not c.activo:
        if borrador.activo:
            return "configurado", "Configurado", "La activación está en borrador: falta aprobarla."
        return "desactivado", "Desactivado", "El blog no aparece en la web."
    from publicacion.motor import conectado
    if not conectado(sitio):
        return "aprobado", "Aprobado", "La web de este sitio todavía no está conectada al generador común."
    if ultimo_ok and c.last_published_at and c.last_published_at <= ultimo_ok.finalizado:
        detalle = "En la web." + (" Hay cambios de configuración sin aprobar." if c.has_unpublished_changes else "")
        return "publicado", "Publicado", detalle
    return "aprobado", "Aprobado", "Se ve en la web después de «Publicar en la web»."


def estado_editorial(a):
    if a.workflow_in_progress:
        return "revision", "En revisión"
    if a.live and a.has_unpublished_changes:
        return "cambios", "Aprobado · cambios en borrador"
    if a.live:
        return "aprobado", "Aprobado"
    return "borrador", "Borrador"


def estado_web(a, blog_clave, ultimo_ok):
    """Si el artículo está efectivamente en la web, según el blog del sitio y la última publicación que terminó bien."""
    if not a.live:
        return "no", "No está en la web"
    if blog_clave in ("desactivado", "configurado"):
        return "bloqueado", "Blog sin activar"
    if ultimo_ok and a.last_published_at and a.last_published_at <= ultimo_ok.finalizado and blog_clave == "publicado":
        return "web", "Publicado"
    return "falta", "Falta publicar"


def estado_articulo_html(articulo):
    """Contenido de la pestaña «Publicación» del editor."""
    if not articulo.pk:
        return mark_safe("<p>El artículo nuevo queda como <b>borrador</b>. Nada se publica sin aprobación: después de aprobarlo, "
                         "aparece en la web con «Publicar en la web», si el blog del sitio está activo.</p>")
    from contenidos.models import sitio_de_pagina
    sitio = sitio_de_pagina(articulo)
    if sitio is None:
        return ""
    ultimo = ultimo_despliegue(sitio)
    bc, bt, bd = estado_blog(sitio, ultimo)
    _ec, et = estado_editorial(articulo)
    _wc, wt = estado_web(articulo, bc, ultimo)
    fecha = ultimo.finalizado.strftime("%d/%m/%Y %H:%M") if ultimo else "nunca"
    from django.urls import reverse
    return format_html(
        '<dl class="gwa-estado-art"><dt>Estado editorial</dt><dd>{}</dd><dt>En la web</dt><dd>{}</dd>'
        '<dt>Blog de {}</dt><dd>{}. {}</dd><dt>Última publicación de la web</dt><dd>{}</dd></dl>'
        '<p class="gwa-estado-acc"><a class="gu-btn gu-btn-outline gu-btn-sm" href="{}" target="_blank" rel="noopener">Vista previa</a> '
        '<a class="gu-btn gu-btn-ghost gu-btn-sm" href="{}">Historial</a> <a class="gu-btn gu-btn-ghost gu-btn-sm" href="{}">Volver al blog</a></p>'
        '<p>Para aprobar: «Enviar a aprobación» (o «Publicar», si tenés permiso) en la barra de abajo. Aprobar no cambia la web: '
        'el artículo aparece después de «Publicar en la web», si el blog del sitio está activo.</p>',
        et, wt, sitio.nombre, bt, bd, fecha,
        reverse("wagtailadmin_pages:view_draft", args=[articulo.pk]), reverse("wagtailadmin_pages:history", args=[articulo.pk]),
        reverse("blog:index") + f"?sitio={sitio.clave}")
