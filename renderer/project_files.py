"""Archivos de proyecto de cada sitio comercial: README, workflow de publicación, CNAME de ejemplo."""

WORKFLOW = """name: Publicar en GitHub Pages
# Sitio estático: se publica la carpeta tal cual. Solo corre a mano (workflow_dispatch)
# para que nada se publique hasta que se decida el lanzamiento.
on:
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - id: deployment
        uses: actions/deploy-pages@v4
"""

README = """# {name} · sitio comercial

Landing comercial completa de **{name}**, producto de la Cooperativa GENEOS.
Dominio previsto: **{dom_label}**. Todavía **no está publicada**.

Es un sitio estático e independiente: no depende de archivos ni rutas del sitio de GENEOS.
Las rutas son relativas, así que funciona en la raíz de un dominio, en una subcarpeta
o con un servidor local.

## Estructura

- `index.html`: la landing completa (hero, cómo funciona, módulos, planes y precios, preguntas frecuentes, formulario de demo){pages_note}.
- `assets/css/`: `styles.css` (base visual de GENEOS), `product.css` (componentes de producto y temas de color) y `site.css` (header y footer propios).
- `assets/js/`: `main.js` (menú móvil, marquesina de logos), `product.js` (formulario de demo por WhatsApp y preguntas frecuentes) y `site.js` (cierra el menú móvil al elegir una opción).
- `assets/img/`, `assets/descargas/`: solo las imágenes y archivos que usa la página.
- `404.html`, `robots.txt`{sitemap_item}.
- `.github/workflows/pages.yml`: publicación en GitHub Pages (se ejecuta a mano).

## Cómo se genera

Este sitio se genera desde la carpeta `GENEOS WEB/tools/sitios-comerciales/`. Los datos comerciales y de contacto
se editan en un solo lugar (`data/contacto.json` y, para GERP, `data/gerp.json`) y se vuelve a exportar:

```bash
cd ~/Documents/"GENEOS WEB" && python3 build.py && python3 tools/sitios-comerciales/export.py {key}
```

Editar a mano los `index.html` funciona, pero la próxima exportación pisa esos cambios.

## Ver localmente

```bash
python3 -m http.server 8000
```

y abrir http://localhost:8000/

## Editar

- Textos, precios, módulos y contacto: en `tools/sitios-comerciales/data/` (ver «Cómo se genera»).
- Colores del header: `assets/css/site.css`, bloque `.pp-theme-{key}` (variables `--hd-*`).
- Colores del producto: `assets/css/product.css`, bloque `.pp-theme-{key}`.
- Formulario de demo: arma un mensaje de WhatsApp al +54 9 249 452-1418 (`assets/js/product.js`). Cuando exista un backend, cambiar el `action` del formulario.

## Publicar (cuando se decida)

1. Crear un repositorio nuevo (por ejemplo `{folder}`) y subir esta carpeta.
2. En el repositorio: Settings → Pages → Source: **GitHub Actions**, y ejecutar el workflow "Publicar en GitHub Pages" desde la pestaña Actions.
3. Revisar el sitio en la dirección de prueba de GitHub Pages. Mientras sea de prueba, cambiar en `index.html` el meta `robots` a `noindex, nofollow`.
4. Para usar {dom_label}: {cname_step}, cargar el dominio en Settings → Pages → Custom domain y apuntar el DNS a GitHub Pages (registros A a 185.199.108.153, 185.199.109.153, 185.199.110.153 y 185.199.111.153, o un CNAME de `www` a `<usuario>.github.io`). **Esto reemplaza la web que hoy esté publicada en ese dominio: hacerlo solo al lanzar.**
5. Volver `robots` a `index, follow` y dar de alta el dominio en Google Search Console con `sitemap.xml`.
{pending}"""

PENDING = """
## Dominio pendiente

Al definir el dominio de {name}: agregar en `index.html` el `<link rel="canonical">` y el `og:url`,
completar la línea `Sitemap:` de `robots.txt` y crear `sitemap.xml`.
"""


GEAGRO_README = """
## Páginas y URL (iguales a las del sitio publicado en geagro.ar)

| URL | Archivo | Palabra clave principal |
|---|---|---|
| `/` | `index.html` | software de gestión agropecuaria |
| `/cereales/` | `cereales/index.html` | software de gestión agrícola · gestión de cereales |
| `/vid/` | `vid/index.html` | software para gestión de viñedos · gestión vitivinícola |
| `/campo/` | `campo/index.html` | dirección anterior: redirige a `/cereales/` (noindex + canónica) |

Se conservan además las URL de recursos del sitio publicado: `assets/docs/Brochure-GEAGRO*.pdf`,
`assets/images/...` (incluidas las imágenes para redes `og-*.jpg`), `favicon.ico` y `assets/icons/favicon/`.
Las fuentes (Titillium Web, licencia OFL) están en `assets/fonts/`; los fondos grandes tienen versión AVIF con respaldo WebP.

## Lanzamiento (reemplaza la web actual de geagro.ar: hacerlo solo cuando se decida)

1. El repositorio publicado (`sorensenclara/geagro-web`) tiene el sitio actual: subir este contenido en una rama nueva
   y revisar antes de llevarlo a `main`. Conservar el archivo `CNAME` con `geagro.ar`.
2. Verificar que respondan `/`, `/cereales/`, `/vid/`, `/campo/` (redirige), los tres PDF y `sitemap.xml`.
3. En Google Search Console: enviar `sitemap.xml` y revisar el informe de páginas por si hubiera otras URL indexadas.
"""


def write_project_files(out, P):
    dom = P["domain"].replace("https://", "") if P["domain"] else ""
    (out / ".gitignore").write_text(".DS_Store\n*.tmp\n")
    (out / ".nojekyll").write_text("")
    if dom:
        (out / "CNAME.example").write_text(dom + "\n")
    wf = out / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "pages.yml").write_text(WORKFLOW)
    (out / "README.md").write_text(README.format(
        name=P["name"], key=P["key"], folder=P["folder"],
        pages_note="; en GEAGRO también `cereales/index.html` y `vid/index.html`" if P["key"] == "geagro" else "",
        dom_label=dom or "a definir",
        sitemap_item=" y `sitemap.xml`" if dom else "",
        cname_step="renombrar `CNAME.example` a `CNAME`" if dom else "crear un archivo `CNAME` con el dominio",
        pending=(GEAGRO_README if P["key"] == "geagro" else "") + ("" if dom else PENDING.format(name=P["name"]))))
