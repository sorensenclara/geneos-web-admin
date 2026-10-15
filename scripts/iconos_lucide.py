"""Genera los íconos lineales (Lucide) del administrador.

Reemplaza los íconos de Wagtail por su equivalente de Lucide con el mismo nombre
(templates/wagtailadmin/icons/<nombre>.svg tiene prioridad sobre los de Wagtail)
y agrega los que usa el sistema de diseño (templates/gwa/iconos/<nombre>.svg).

Uso (solo cuando se agregan íconos; los SVG generados quedan en el repositorio):
    npm pack lucide-static@0.460.0 && tar xzf lucide-static-0.460.0.tgz
    python scripts/iconos_lucide.py package/icons
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TRAZO = "1.8"  # mismo grosor de línea que los íconos de GELECTRIC

# Nombre de Wagtail → ícono de Lucide
WAGTAIL = {
    "arrow-down": "chevron-down", "arrow-left": "chevron-left", "arrow-right": "chevron-right", "arrow-up": "chevron-up",
    "arrow-right-full": "arrow-right", "bars": "menu", "bin": "trash-2", "bold": "bold", "breadcrumb-expand": "chevrons-right",
    "calendar": "calendar", "calendar-alt": "calendar-days", "calendar-check": "calendar-check", "check": "check",
    "circle-check": "circle-check", "circle-plus": "circle-plus", "circle-xmark": "circle-x", "clipboard-list": "clipboard-list",
    "code": "code", "cog": "settings", "cogs": "settings-2", "collapse-down": "chevrons-up-down", "collapse-up": "chevrons-down-up",
    "comment": "message-square", "comment-add": "message-square-plus", "comment-add-reversed": "message-square-plus",
    "copy": "copy", "cross": "x", "crosshairs": "crosshair", "cut": "scissors", "date": "calendar", "decimal": "hash",
    "desktop": "monitor", "doc-empty": "file", "doc-empty-inverse": "file", "doc-full": "file-text", "doc-full-inverse": "file-text",
    "dots-horizontal": "ellipsis", "download": "download", "draft": "file-pen-line", "edit": "pencil", "error": "circle-x",
    "expand-right": "chevrons-right", "folder": "folder", "folder-inverse": "folder", "folder-open-1": "folder-open",
    "folder-open-inverse": "folder-open", "form": "list", "glasses": "glasses", "globe": "globe", "grid": "layout-grid",
    "grip": "grip-vertical", "group": "users", "h1": "heading-1", "h2": "heading-2", "h3": "heading-3", "h4": "heading-4",
    "h5": "heading-5", "h6": "heading-6", "help": "circle-help", "history": "history", "home": "house", "image": "image",
    "info-circle": "info", "italic": "italic", "key": "key-round", "keyboard": "keyboard", "link": "link",
    "link-external": "external-link", "list-ol": "list-ordered", "list-ul": "list", "lock": "lock", "lock-open": "lock-open",
    "login": "log-in", "logout": "log-out", "mail": "mail", "media": "circle-play", "minus": "minus", "mobile-alt": "smartphone",
    "no-view": "eye-off", "openquote": "quote", "order": "arrow-down-1-0", "order-down": "arrow-down", "order-up": "arrow-up",
    "password": "key-round", "pick": "star", "pilcrow": "pilcrow", "placeholder": "circle-chevron-down", "plus": "plus",
    "plus-inverse": "circle-plus", "radio-empty": "circle", "radio-full": "circle-dot", "redirect": "corner-up-right",
    "regex": "regex", "resubmit": "arrow-left-right", "rotate": "rotate-cw", "search": "search", "site": "earth",
    "sliders": "sliders-horizontal", "snippet": "puzzle", "spinner": "loader-circle", "strikethrough": "strikethrough",
    "subscript": "subscript", "success": "circle-check", "superscript": "superscript", "table": "table", "tablet-alt": "tablet",
    "tag": "tag", "tasks": "list-checks", "thumbtack": "pin", "thumbtack-crossed": "pin-off", "tick-inverse": "square-check-big",
    "time": "clock", "title": "heading", "upload": "upload", "user": "user", "view": "eye", "wagtail": "layout-dashboard",
    "warning": "triangle-alert",
}

# Íconos propios del sistema de diseño (no existen en Wagtail)
PROPIOS = ["megaphone", "network", "inbox", "panel-left", "chevron-down", "chevron-right", "user-round", "log-out",
           "circle-alert", "pencil-line", "save", "send", "package", "circle-minus", "type", "list-filter", "table-2", "list"]


def iconos_funcionalidad():
    """Íconos elegibles para una funcionalidad (contenidos/iconos_funcionalidad.py), como «f-<nombre>»."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("iconos", RAIZ / "contenidos" / "iconos_funcionalidad.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {f"f-{n}": n for n in mod.NOMBRES}


def simbolo(origen: Path, nombre: str) -> str:
    svg = origen.read_text()
    cuerpo = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    cuerpo = re.sub(r"<!--.*?-->", "", cuerpo, flags=re.S)
    cuerpo = " ".join(cuerpo.split()).replace(" />", "/>")
    # La palabra «svg» no puede aparecer adentro: Wagtail convierte cada «svg» en «symbol» al armar el sprite.
    assert "svg" not in cuerpo, nombre
    return (f'<svg id="icon-{nombre}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="{TRAZO}" stroke-linecap="round" stroke-linejoin="round"><!-- Lucide {origen.stem} (ISC) -->{cuerpo}</svg>\n')


def main(dir_lucide: str):
    lucide = Path(dir_lucide)
    destinos = [(RAIZ / "templates/wagtailadmin/icons", WAGTAIL), (RAIZ / "templates/gwa/iconos", {n: n for n in PROPIOS}),
                (RAIZ / "templates/gwa/iconos", iconos_funcionalidad())]
    for carpeta, mapa in destinos:
        carpeta.mkdir(parents=True, exist_ok=True)
        for nombre, origen in mapa.items():
            (carpeta / f"{nombre}.svg").write_text(simbolo(lucide / f"{origen}.svg", nombre))
    print(f"{len(WAGTAIL)} íconos de Wagtail reemplazados, {len(PROPIOS)} propios y {len(iconos_funcionalidad())} para funcionalidades.")


if __name__ == "__main__":
    main(sys.argv[1])
