"""Permisos por sitio y por línea para los contenidos que no son páginas (planes, FAQ, testimonios, pedidos…).

Wagtail asigna permisos de snippets por modelo; esta política los acota al sitio y a la línea de cada objeto,
y se aplica en el servidor en todas las vistas (listado, edición, publicación, borrado).
"""
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.urls import URLPattern
from django.db.models import Q
from wagtail.permission_policies.base import BasePermissionPolicy

from .models import NIVEL, AccesoSitio

NIVEL_MINIMO = {"view": 1, "add": 1, "change": 1, "lock": 1, "unlock": 2, "publish": 2, "delete": 3}


def accesos(user):
    """[(sitio_id, linea_id | None, nivel)] del usuario."""
    if not user.is_authenticated:
        return []
    if not hasattr(user, "_gwa_accesos"):
        user._gwa_accesos = [(a.sitio_id, a.linea_id, NIVEL[a.rol])
                             for a in AccesoSitio.objects.filter(grupo__in=user.groups.all())]
    return user._gwa_accesos


def sitios_permitidos(user, nivel=1):
    """IDs de sitios en los que el usuario tiene al menos ese nivel (None = todos)."""
    if user.is_superuser:
        return None
    return {s for s, _l, n in accesos(user) if n >= nivel}


def puede(user, sitio_id, linea_id=None, nivel=1):
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    for s, l, n in accesos(user):
        if s == sitio_id and n >= nivel and (l is None or l == linea_id):
            return True
    return False


class SitioPermissionPolicy(BasePermissionPolicy):
    def __init__(self, model):
        super().__init__(model)
        self.tiene_linea = any(f.name == "linea" for f in model._meta.get_fields())

    def _nivel(self, action):
        return NIVEL_MINIMO.get(action, 3)

    def user_has_permission(self, user, action):
        if not user.is_authenticated or not user.is_active:
            return False
        return user.is_superuser or any(n >= self._nivel(action) for _s, _l, n in accesos(user))

    def user_has_permission_for_instance(self, user, action, instance):
        linea = getattr(instance, "linea_id", None) if self.tiene_linea else None
        return puede(user, instance.sitio_id, linea, self._nivel(action))

    def instances_user_has_any_permission_for(self, user, actions):
        qs = self.model._default_manager.all()
        if not user.is_authenticated or not user.is_active:
            return qs.none()
        if user.is_superuser:
            return qs
        nivel = min(self._nivel(a) for a in actions)
        cond = Q(pk__in=[])
        for s, l, n in accesos(user):
            if n >= nivel:
                c = Q(sitio_id=s)
                if l is not None and self.tiene_linea:
                    c &= Q(linea_id=l)
                cond |= c
        return qs.filter(cond)

    def users_with_any_permission(self, actions):
        nivel = min(self._nivel(a) for a in actions)
        grupos = [a.grupo_id for a in AccesoSitio.objects.all() if NIVEL[a.rol] >= nivel]
        return get_user_model().objects.filter(Q(is_superuser=True) | Q(groups__in=grupos), is_active=True).distinct()

    def users_with_any_permission_for_instance(self, actions, instance):
        nivel = min(self._nivel(a) for a in actions)
        linea = getattr(instance, "linea_id", None) if self.tiene_linea else None
        grupos = [a.grupo_id for a in AccesoSitio.objects.filter(sitio_id=instance.sitio_id)
                  if NIVEL[a.rol] >= nivel and (a.linea_id is None or a.linea_id == linea)]
        return get_user_model().objects.filter(Q(is_superuser=True) | Q(groups__in=grupos), is_active=True).distinct()


class ProtegerObjetos:
    """Para los ViewSets: toda vista de un objeto concreto (editar, borrar, historial, vista previa…)
    verifica en el servidor que el objeto sea de un sitio y línea del usuario."""

    ACCION_POR_VISTA = {"delete": "delete", "unpublish": "publish", "unlock": "unlock", "revisions_unschedule": "publish",
                        "revisions_revert": "change", "lock": "lock"}

    def get_urlpatterns(self):
        """Toda vista de un objeto concreto (editar, borrar, historial, vista previa…) verifica que sea de un sitio y línea del usuario."""
        res = []
        for u in super().get_urlpatterns():
            if isinstance(u, URLPattern) and "pk" in str(u.pattern):
                u = URLPattern(u.pattern, self._proteger(u.callback, self.ACCION_POR_VISTA.get(u.name, "change")), u.default_args, u.name)
            res.append(u)
        return res

    def _proteger(self, vista, accion):
        viewset = self

        @wraps(vista)
        def protegida(request, *args, **kwargs):
            obj = viewset.model._default_manager.filter(pk=kwargs.get("pk")).first()
            if obj is not None and not viewset.permission_policy.user_has_permission_for_instance(request.user, accion, obj):
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return protegida

