"""Integración con un proveedor de IA para ideas y esquemas. APAGADA por defecto.

Se habilita solo con las tres variables de entorno del servidor (nunca en el frontend ni en el repositorio):
  GWA_IA_PROVEEDOR=anthropic   GWA_IA_MODELO=<modelo>   GWA_IA_LIMITE_USD=<tope mensual, p. ej. 5>
y la clave en ANTHROPIC_API_KEY. Sin cualquiera de ellas, la pantalla funciona en «modo demostración»:
tendencias importadas e ideas editoriales de los contenidos propios, sin ninguna llamada externa.

Antes de cada pedido se verifica que el gasto estimado no supere el límite del mes; después se registra el consumo real
informado por el proveedor (ConsumoIA). Las respuestas se validan: se descartan las ideas con cifras, porcentajes o
volúmenes, y todas se guardan como «Idea de IA».
"""
import json
import os
import re
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .models import ConsumoIA, IdeaEditorial

# US$ por millón de tokens (entrada, salida). Configurable en settings.GWA_IA_PRECIOS; verificar la lista vigente del proveedor.
PRECIOS = {"claude-sonnet": (Decimal("2"), Decimal("10")), "claude-haiku": (Decimal("0.10"), Decimal("0.50"))}


class IADesactivada(Exception):
    pass


class LimiteAlcanzado(Exception):
    pass


def configuracion():
    return {"proveedor": os.environ.get("GWA_IA_PROVEEDOR", "").strip().lower(),
            "modelo": os.environ.get("GWA_IA_MODELO", "").strip(),
            "limite": Decimal(os.environ.get("GWA_IA_LIMITE_USD", "0") or "0"),
            "clave": bool(os.environ.get("ANTHROPIC_API_KEY"))}


def gasto_del_mes():
    hoy = timezone.localdate()
    total = ConsumoIA.objects.filter(creado__year=hoy.year, creado__month=hoy.month).aggregate(t=Sum("costo_usd"))["t"]
    return total or Decimal("0")


def estado():
    c = configuracion()
    activa = c["proveedor"] == "anthropic" and c["modelo"] and c["clave"] and c["limite"] > 0
    gasto = gasto_del_mes()
    return {"activa": bool(activa), "modo": "IA conectada" if activa else "Modo demostración · sin consumo",
            "proveedor": c["proveedor"] or "sin configurar", "modelo": c["modelo"], "limite": c["limite"], "gasto": gasto,
            "disponible": bool(activa) and gasto < c["limite"]}


def _precio(modelo):
    tabla = getattr(settings, "GWA_IA_PRECIOS", PRECIOS)
    for prefijo, p in tabla.items():
        if modelo.startswith(prefijo):
            return p
    return (Decimal("5"), Decimal("25"))  # modelo desconocido: estimación conservadora para no pasar el límite


def costo(modelo, entrada, salida):
    pe, ps = _precio(modelo)
    return (pe * entrada + ps * salida) / Decimal(1_000_000)


CIFRAS = re.compile(r"\d+\s*(%|por ciento|mil|millones|búsquedas|busquedas|visitas)|volumen|posición \d", re.I)


def _llamar(prompt, max_tokens, sitio, usuario, tarea, enviar=None):
    st = estado()
    if not st["activa"]:
        raise IADesactivada("La IA no está habilitada. Se muestran tendencias importadas e ideas editoriales.")
    modelo = st["modelo"]
    estimado = costo(modelo, len(prompt) // 3, max_tokens)
    if st["gasto"] + estimado > st["limite"]:
        raise LimiteAlcanzado(f"Se alcanzó el límite mensual de US$ {st['limite']}. El pedido no se envió.")
    cuerpo = {"model": modelo, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    enviar = enviar or _enviar_anthropic
    try:
        resp = enviar(cuerpo)
    except Exception:
        ConsumoIA.objects.create(sitio=sitio, proveedor="anthropic", modelo=modelo, tarea=tarea, ok=False, usuario=usuario)
        raise
    uso = resp.get("usage", {})
    ent, sal = int(uso.get("input_tokens", 0)), int(uso.get("output_tokens", 0))
    ConsumoIA.objects.create(sitio=sitio, proveedor="anthropic", modelo=modelo, tarea=tarea, tokens_entrada=ent, tokens_salida=sal,
                             costo_usd=costo(modelo, ent, sal), usuario=usuario)
    return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")


def _enviar_anthropic(cuerpo):
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(cuerpo).encode(),
                                 headers={"content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                          "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _contexto(sitio, linea, config):
    from .ideas import candidatas_internas, _articulos
    temas = [c["termino"] for c in candidatas_internas(sitio)][:40]
    publicados = list(_articulos(sitio).values_list("title", flat=True)[:60])
    return (f"Producto: {sitio.nombre}{' ' + linea.nombre if linea else ''}. Temas del blog: {config.temas if config else ''}. "
            f"No incluir: {config.excluir if config else ''}. Funcionalidades, sectores y preguntas reales: {'; '.join(temas)}. "
            f"Artículos existentes (no repetir): {'; '.join(publicados)}.")


def sugerir_ideas(sitio, usuario=None, linea=None, cantidad=10, enviar=None):
    """Pide ideas al proveedor. Devuelve las IdeaEditorial creadas (tipo «ia»)."""
    from .ideas import _excluida
    from .models import config_actual
    config = config_actual(sitio)
    prompt = (f"Sos editor de contenidos de una cooperativa de software argentina. {_contexto(sitio, linea, config)}\n"
              f"Proponé {cantidad} temas de artículos para Argentina. No inventes datos, cifras, porcentajes, volúmenes de búsqueda, "
              "tendencias, normativas ni funciones del software. Respondé solo un JSON: "
              '[{"titulo": "...", "motivo": "...", "palabras_clave": "...", "intencion": "Informativa|Comercial"}]')
    texto = _llamar(prompt, 1500, sitio, usuario, "ideas", enviar=enviar)
    m = re.search(r"\[.*\]", texto, re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = []
    hoy, creadas = timezone.localdate(), []
    for it in items[:cantidad]:
        titulo, motivo = str(it.get("titulo", ""))[:160], str(it.get("motivo", ""))
        if not titulo or CIFRAS.search(titulo + " " + motivo) or _excluida(titulo + " " + motivo, config):
            continue
        creadas.append(IdeaEditorial.objects.create(sitio=sitio, linea=linea, tipo="ia", titulo=titulo, descripcion=motivo[:600],
                                                    palabras_clave=str(it.get("palabras_clave", ""))[:250], intencion=str(it.get("intencion", ""))[:40],
                                                    fuente="Sugerencia de IA · sin datos de búsqueda", consultado=hoy,
                                                    clave=f"ia:{titulo.lower()[:180]}"))
    return creadas
