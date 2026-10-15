"""Sectores: dónde aparecen en cada web y los que se cargan al inicializar.

Los textos de GEMA son los que la web publica hoy en «¿Para quién es GEMA?» (renderer/tpl/gema.html): pasan a
administrarse desde «Oferta comercial → Sectores» sin cambiar lo publicado. GEAGRO no tiene sección de sectores
en su web: sus sectores quedan como borrador interno, sin textos comerciales nuevos."""

# Productos cuya web tiene una sección de tarjetas de sectores (la plantilla la contempla)
SECCION_WEB = {
    "gerp": "Tarjetas «Pensado para tu sector» de la home de GERP.",
    "gema": "Tarjetas «¿Para quién es GEMA?» de la home de GEMA.",
}
SIN_SECCION = ("La web de {producto} no tiene una sección de sectores: lo que cargues acá queda como información interna y no se publica. "
               "El público de cada línea se menciona hoy en la portada de cada página (Páginas) y en las preguntas frecuentes.")

GEMA = [
    {"nombre": "Talleres de matafuegos", "titulo": "Talleres de recarga", "icono": "bi-wrench-adjustable",
     "texto": "Talleres de recarga y mantenimiento de matafuegos que necesitan controlar vencimientos y servicios."},
    {"nombre": "Empresas de servicios", "titulo": "Empresas de servicios", "icono": "bi-buildings",
     "texto": "Empresas de seguridad contra incendios que atienden a comercios, industrias, consorcios e instituciones."},
    {"nombre": "Distribuidores", "titulo": "Distribuidores", "icono": "bi-shop",
     "texto": "Distribuidores de matafuegos que quieren seguir los equipos de sus clientes y avisarles a tiempo."},
]
# Sin textos comerciales: todavía no están validados
GEAGRO = [{"nombre": "Agrario", "titulo": "Agrario", "linea": "cereales"},
          {"nombre": "Viñedos", "titulo": "Viñedos", "linea": "vid"}]


def seccion_web(sitio):
    return SECCION_WEB.get(sitio.clave) or SIN_SECCION.format(producto=sitio.nombre)
