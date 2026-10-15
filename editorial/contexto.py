"""Línea elegida en «Blog y noticias» para un artículo nuevo: llega al formulario de Wagtail sin pasar por la URL del editor."""
from contextvars import ContextVar

_linea = ContextVar("gwa_linea_inicial", default=None)


def fijar_linea(linea_id):
    _linea.set(linea_id)


def linea_inicial():
    return _linea.get()
