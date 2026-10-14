"""API pública del formulario de demo: token anti-bots, validación, registro y aviso por email.

Medidas: campo trampa, tiempo mínimo de llenado con token firmado, límite de envíos por IP (huella anónima),
orígenes permitidos (CORS), tamaño máximo, consentimiento obligatorio. No se guarda la IP.
"""
import hashlib
import json

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from sitios.models import SitioWeb

from .models import SolicitudDemo

SAL = "gwa-formulario-demo"
LIMITES = {"nombre": 120, "empresa": 120, "email": 254, "telefono": 40, "localidad": 120, "superficie": 20, "mensaje": 3000, "producto": 60, "plan": 60, "pagina": 200}


def origenes_permitidos():
    o = set(settings.GWA_CORS_EXTRA)
    for s in SitioWeb.objects.exclude(dominio=""):
        o.add(s.dominio.rstrip("/"))
    return o


def _cors(request, resp):
    origen = request.headers.get("Origin")
    if origen and origen in origenes_permitidos():
        resp["Access-Control-Allow-Origin"] = origen
        resp["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp["Access-Control-Allow-Headers"] = "Content-Type"
        resp["Vary"] = "Origin"
    return resp


def _huella(request):
    ip = request.META.get("REMOTE_ADDR", "")
    return hashlib.sha256((settings.SECRET_KEY + ip).encode()).hexdigest()


@csrf_exempt
def token(request):
    if request.method == "OPTIONS":
        return _cors(request, JsonResponse({}))
    sitio = request.GET.get("sitio", "")[:20]
    return _cors(request, JsonResponse({"token": signing.dumps({"s": sitio, "t": timezone.now().timestamp()}, salt=SAL)}))


@csrf_exempt
def recibir(request):
    if request.method == "OPTIONS":
        return _cors(request, JsonResponse({}))
    if request.method != "POST":
        return _cors(request, JsonResponse({"error": "Método no permitido."}, status=405))
    origen = request.headers.get("Origin")
    if origen and origen not in origenes_permitidos():
        return JsonResponse({"error": "Origen no permitido."}, status=403)
    if len(request.body) > 20000:
        return _cors(request, JsonResponse({"error": "El mensaje es demasiado largo."}, status=413))
    try:
        d = json.loads(request.body)
    except ValueError:
        return _cors(request, JsonResponse({"error": "Datos inválidos."}, status=400))
    huella = _huella(request)
    clave = f"gwa-demo-{huella}"
    if cache.get(clave, 0) >= settings.GWA_FORM_MAX_POR_HORA:
        return _cors(request, JsonResponse({"error": "Recibimos varios pedidos seguidos. Probá más tarde."}, status=429))
    # Campo trampa: los bots lo completan. Respondemos OK sin guardar nada.
    if d.get("sitio_web"):
        return _cors(request, JsonResponse({"ok": True}))
    try:
        tk = signing.loads(d.get("token", ""), salt=SAL, max_age=7200)
        if timezone.now().timestamp() - tk["t"] < settings.GWA_FORM_SEGUNDOS_MINIMOS:
            raise signing.BadSignature("demasiado rápido")
    except signing.BadSignature:
        return _cors(request, JsonResponse({"error": "No pudimos validar el formulario. Recargá la página e intentá de nuevo."}, status=400))
    sitio = SitioWeb.objects.filter(clave=d.get("sitio", ""), usa_formularios=True).first()
    if sitio is None:
        return _cors(request, JsonResponse({"error": "Formulario no disponible."}, status=400))
    datos = {k: str(d.get(k, "")).strip()[:n] for k, n in LIMITES.items()}
    datos["plan"] = str(d.get("plan") or d.get("version") or "").strip()[:60]
    errores = []
    if not datos["nombre"]:
        errores.append("Completá tu nombre.")
    try:
        validate_email(datos["email"])
    except Exception:
        errores.append("Revisá el email.")
    if not d.get("consentimiento"):
        errores.append("Necesitamos tu consentimiento para responderte.")
    if errores:
        return _cors(request, JsonResponse({"error": " ".join(errores)}, status=400))
    s = SolicitudDemo.objects.create(sitio=sitio, consentimiento=timezone.now(), ip_hash=huella, **datos)
    cache.set(clave, cache.get(clave, 0) + 1, 3600)
    try:
        cuerpo = "\n".join(f"{k.capitalize()}: {v}" for k, v in datos.items() if v)
        send_mail(f"Pedido de demo · {datos['producto'] or sitio.nombre}", cuerpo + "\n\nVer en el administrador: /admin/", settings.DEFAULT_FROM_EMAIL,
                  [sitio.email_pedidos], fail_silently=False)
        s.email_enviado = True
        s.save(update_fields=["email_enviado"])
    except Exception:  # el pedido queda registrado aunque falle el email
        pass
    return _cors(request, JsonResponse({"ok": True}))
