"""Identidad visual de cada producto en el administrador.

Los isologos son los archivos oficiales (static/gwa/marca, copias sin modificar de docs/marca)
y el color es el del isologo de cada producto.
"""
from django.templatetags.static import static

GENEOS_VERDE = "#128237"  # verde del isologotipo de GENEOS

PRODUCTOS = {
    "geneos": {"isologo": "gwa/marca/geneos-isologo-color.svg", "color": GENEOS_VERDE, "lema": "Cooperativa de software libre"},
    "gerp": {"isologo": "gwa/marca/gerp-isologo.svg", "color": "#1b4b8c", "lema": "Software de gestión empresarial"},
    "geagro": {"isologo": "gwa/marca/geagro-isologo.svg", "color": "#0e8337", "lema": "Software de gestión agropecuaria"},
    "gema": {"isologo": "gwa/marca/gema-isologo.svg", "color": "#ec6c05", "lema": "Plataforma de gestión de matafuegos"},
}


def marca(clave):
    datos = PRODUCTOS.get(clave)
    if not datos:
        return None
    return {**datos, "isologo_url": static(datos["isologo"])}
