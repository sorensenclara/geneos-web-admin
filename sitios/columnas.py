"""Columna de listados que identifica el producto con su isologo oficial (sitios/marca.py)."""
from wagtail.admin.ui.tables import Column


class ColumnaSitio(Column):
    cell_template_name = "gwa/ui/celda_sitio.html"

    def __init__(self, name="sitio", label="Sitio", accessor="sitio", sort_key="sitio__nombre", **kwargs):
        super().__init__(name, label=label, accessor=accessor, sort_key=sort_key, **kwargs)


def columna_sitio():
    return ColumnaSitio()
