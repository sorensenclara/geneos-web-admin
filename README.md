# GENEOS Web Admin

Administrador centralizado de contenidos para los sitios web de GENEOS (GENEOS institucional, GERP, GEAGRO Cereales y Vid, GEMA).
Wagtail + PostgreSQL; los sitios públicos siguen siendo estáticos y se generan con el motor de plantillas actual.

**Estado:** propuesta en revisión. Todavía no hay implementación: este repositorio contiene la propuesta y el prototipo con el que se probó el circuito de publicación.

- `docs/propuesta.html`: propuesta técnica completa (auditoría, arquitectura, modelo de datos, mockups, hosting, plan, migración).
- `prototipo-publicacion/`: app de Django/Wagtail usada para probar Editar → Borrador → Vista previa → Aprobación → Publicación → Web pública, y el caso de despliegue fallido.

Este repositorio es independiente de los sistemas Django operativos de GENEOS y de los repositorios de las webs.

## Probar el prototipo

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install "wagtail>=7.4,<7.5" "django>=5.2,<6.1" jinja2 pillow
wagtail start webadmin poc && cd poc
cp -r ../prototipo-publicacion/publishing .
```

Agregar `"publishing"` a `INSTALLED_APPS` y estas variables en `webadmin/settings/base.py`:

```python
WEB_TOOLS_DIR = "/ruta/a/GENEOS WEB/tools/sitios-comerciales"   # exportador (debe aceptar WEB_DATA_DIR)
WEB_PUBLIC_ROOT = "/ruta/a/carpeta-publica-de-prueba"
WEB_PREVIEW_ROOT = "/ruta/a/carpeta-de-vistas-previas"
```

y en `webadmin/urls.py`, antes de las rutas de Wagtail, la ruta privada de vistas previas:

```python
path("__preview/<path:path>", staff_member_required(static_serve), {"document_root": settings.WEB_PREVIEW_ROOT}),
```

El exportador del prototipo lee los datos desde la variable de entorno `WEB_DATA_DIR` (cambio de 2 líneas en `export.py`, pendiente de incorporar en la rama `2026` de GENEOS WEB).
