"""Si el sitio lo tiene activado y publica en la carpeta local, cada aprobación actualiza esa copia automáticamente."""
from wagtail.signals import page_published, published


def _auto(instance, user):
    from .servicio import publicar_sitio, sitio_de
    sitio = sitio_de(instance)
    # Solo hacia la carpeta local: una web que ve otra gente se publica siempre revisando y confirmando
    if sitio and sitio.publicar_al_aprobar and sitio.motor == "comercial" and not sitio.publica_afuera:
        publicar_sitio(sitio, user, f"Aprobación automática: {instance}")


def al_publicar_pagina(sender, instance, revision=None, **kwargs):
    _auto(instance, getattr(revision, "user", None))


def al_publicar(sender, instance, revision=None, **kwargs):
    _auto(instance, getattr(revision, "user", None))


page_published.connect(al_publicar_pagina, dispatch_uid="gwa_page_published")
published.connect(al_publicar, dispatch_uid="gwa_published")
