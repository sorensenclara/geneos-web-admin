"""Web institucional de GENEOS: secciones administrables de cada página y sus bloques de contenido.

Cada sección tiene una clave estable (su ancla en la plantilla de GENEOS WEB) y textos por defecto en esa plantilla.
Desde acá solo se reemplazan textos, imágenes y enlaces campo por campo: un campo vacío conserva el texto de la web.
El diseño (componentes, colores, columnas, fondos) no se elige acá: lo define la plantilla según la clave.
"""
from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock

# Secciones de cada página, por ruta pública. tipo: bloque que la edita (None: sin textos editables por ahora).
# mover: se puede cambiar de lugar entre las otras que también se mueven. ocultar: se puede ocultar.
SECCIONES = {
    "": [
        {"clave": "hero", "nombre": "Encabezado (hero)", "tipo": None, "mover": False, "ocultar": False},
        {"clave": "soluciones", "nombre": "Productos (Nuestras soluciones)", "tipo": "tarjetas", "mover": True, "ocultar": True},
        {"clave": "servicios", "nombre": "También hacemos (servicios)", "tipo": None, "mover": True, "ocultar": True},
        {"clave": "software-libre", "nombre": "Software libre", "tipo": "tarjetas", "mover": True, "ocultar": True},
        {"clave": "nosotros", "nombre": "Nosotros", "tipo": "texto_imagen", "mover": True, "ocultar": True},
        {"clave": "clientes", "nombre": "Clientes (dentro de Nosotros)", "tipo": "encabezado", "mover": False, "ocultar": True},
        {"clave": "cooperativas", "nombre": "Cooperativas y FACTTIC", "tipo": None, "mover": True, "ocultar": True},
        {"clave": "contacto", "nombre": "Contacto (destino de «Contanos tu proyecto»)", "tipo": "encabezado", "mover": False, "ocultar": False},
    ],
}

# Logos de clientes: páginas donde se muestran (ruta, sección)
PAGINAS_LOGOS = [("", "Inicio")]

# Íconos que ya existen en GENEOS WEB (templates/icons/). Solo se eligen; no se suben íconos nuevos.
ICONOS = [("", "Sin cambios")] + [(n, n) for n in (
    "rol-dev rol-analisis rol-devops rol-pm rol-ux staff gestion apps elearning diseno dev-web gerp gema facturacion inventario ventas "
    "ventaja-costos ventaja-flexible ventaja-profesionales moodle-capacitacion moodle-diseno moodle-gamificacion ui-code "
    "bi-arrows-angle-expand bi-bar-chart-line bi-bell bi-book bi-box bi-box-seam bi-buildings bi-bullseye bi-calendar-check "
    "bi-calendar-event bi-calendar3 bi-cart bi-check-circle bi-check2 bi-check2-circle bi-clipboard-check bi-clipboard-data "
    "bi-clipboard2-plus bi-cloud-arrow-up bi-code-slash bi-coin bi-diagram-3 bi-display bi-eye bi-file-earmark-text bi-files "
    "bi-fire bi-fonts bi-gear bi-gear-wide-connected bi-globe bi-graph-up-arrow bi-headset bi-image bi-info-circle bi-lightbulb "
    "bi-lightning-charge bi-palette bi-pencil bi-people bi-person bi-phone bi-pie-chart bi-puzzle bi-search bi-send "
    "bi-shield-check bi-shop bi-universal-access bi-unlock bi-vector-pen bi-window-stack bi-wrench-adjustable").split()]


def secciones_de(ruta):
    return SECCIONES.get(ruta, [])


def seccion(ruta, clave):
    return next((s for s in secciones_de(ruta) if s["clave"] == clave), None)


def todas_las_claves():
    vistas = {}
    for ruta, lista in SECCIONES.items():
        for s in lista:
            vistas.setdefault(s["clave"], s["nombre"])
    return sorted(vistas.items())


AYUDA_TEXTO = "Vacío: se mantiene el texto actual de la web. **texto** va en negrita."


class ClaveBlock(blocks.ChoiceBlock):
    def __init__(self, **kw):
        super().__init__(choices=todas_las_claves, label="Sección", help_text="Identifica la sección en la plantilla. No se cambia.", **kw)


class SeccionBlock(blocks.StructBlock):
    """Campos comunes: clave y encabezado de la sección. Todos opcionales."""
    clave = ClaveBlock()
    antetitulo = blocks.CharBlock(label="Antetítulo", required=False, max_length=80, help_text="Vacío: se mantiene el actual.")
    titulo = blocks.CharBlock(label="Título", required=False, max_length=120, help_text="Vacío: se mantiene el actual.")
    bajada = blocks.TextBlock(label="Bajada", required=False, help_text=AYUDA_TEXTO)
    boton_texto = blocks.CharBlock(label="Botón: texto", required=False, max_length=60)
    boton_enlace = blocks.CharBlock(label="Botón: enlace", required=False, max_length=200, help_text="/ruta/, #ancla o https://…")


class TarjetaBlock(blocks.StructBlock):
    clave = blocks.CharBlock(label="Clave de la tarjeta", required=False, max_length=40,
                             help_text="No se cambia: une la tarjeta con su diseño. Vacía en las tarjetas nuevas.")
    icono = blocks.ChoiceBlock(choices=ICONOS, label="Ícono", required=False)
    titulo = blocks.CharBlock(label="Título", required=False, max_length=80)
    texto = blocks.TextBlock(label="Texto", required=False, help_text=AYUDA_TEXTO)
    imagen = ImageChooserBlock(label="Imagen", required=False, help_text="Vacía: se mantiene la imagen actual.")
    imagen_alt = blocks.CharBlock(label="Texto alternativo de la imagen", required=False, max_length=200)
    enlace_texto = blocks.CharBlock(label="Enlace: texto", required=False, max_length=60)
    enlace = blocks.CharBlock(label="Enlace: destino", required=False, max_length=200)

    class Meta:
        icon = "doc-empty"
        label = "Tarjeta"


class EncabezadoBlock(SeccionBlock):
    class Meta:
        icon = "title"
        label = "Encabezado de sección"


class TarjetasBlock(SeccionBlock):
    items = blocks.ListBlock(TarjetaBlock(), label="Tarjetas", required=False,
                             help_text="Orden y cantidad de tarjetas. Una tarjeta con campos vacíos conserva los textos actuales.")

    class Meta:
        icon = "list-ul"
        label = "Sección con tarjetas"


class TextoImagenBlock(SeccionBlock):
    texto = blocks.TextBlock(label="Texto", required=False, help_text=AYUDA_TEXTO)
    imagen = ImageChooserBlock(label="Imagen", required=False, help_text="Vacía: se mantiene la imagen actual.")
    imagen_alt = blocks.CharBlock(label="Texto alternativo de la imagen", required=False, max_length=200)

    class Meta:
        icon = "image"
        label = "Sección con texto e imagen"


class PosicionBlock(blocks.StructBlock):
    clave = ClaveBlock()

    class Meta:
        icon = "order"
        label = "Sección sin textos editables (solo posición)"


BLOQUES_SECCION = [("encabezado", EncabezadoBlock()), ("tarjetas", TarjetasBlock()), ("texto_imagen", TextoImagenBlock()),
                   ("posicion", PosicionBlock())]


class DestacadoBlock(blocks.StructBlock):
    clave = blocks.CharBlock(label="Clave", required=False, max_length=40, help_text="No se cambia. Vacía en los destacados nuevos.")
    icono = blocks.ChoiceBlock(choices=ICONOS, label="Ícono", required=False)
    texto = blocks.TextBlock(label="Texto", required=False, help_text="Un renglón por línea. Vacío: se mantiene el actual.")

    class Meta:
        icon = "pick"
        label = "Destacado"
