# GENEOS Web Admin

Administrador centralizado de contenidos de las webs de GENEOS: GENEOS (institucional), GERP, GEAGRO (líneas Cereales y Vid) y GEMA.
Django 6 + Wagtail 7.4 LTS. Las webs públicas siguen siendo estáticas: el administrador genera los archivos con las mismas plantillas de hoy.

**Estado: etapa 1, solo local.** No publica en las webs actuales, no toca dominios ni DNS y no depende de ningún proveedor.
Este repositorio es independiente de los sistemas Django operativos y de los repositorios de las webs (que solo se leen).

## Probarlo en tu Mac

Requisitos: Python 3.12 o más nuevo (`python3 --version`) y la carpeta `GENEOS WEB` al lado de este repositorio
(`~/Documents/GENEOS WEB` y `~/Documents/geneos-web-admin`), con su carpeta `public/` generada como está hoy. El administrador solo lee esa carpeta.

```bash
cd ~/Documents/geneos-web-admin
scripts/iniciar.sh
```

La primera vez crea el entorno, la base local, importa el contenido actual de las webs y te pide usuario y contraseña
(esa es tu cuenta de administradora, con acceso a todo). Después abrí <http://localhost:8000/admin/>.
Para volver a entrar otro día: `scripts/iniciar.sh` de nuevo. Para empezar de cero: borrá la carpeta `var/` y ejecutalo otra vez.

Si GEAGRO no está en la ruta de siempre, copiá `.env.example` como `.env` y completá `GEAGRO_SRC_DIR`.

### Tres pruebas

1. **Editar una página.** Páginas → GERP · Inicio → cambiá el «Título principal» (un renglón por línea; `**así**` va resaltado)
   → *Guardar borrador*. Con el ícono de vista previa (la pantallita, arriba a la derecha) ves la página real con el cambio al costado del formulario, mientras escribís.
   Desde el botón ▲ junto a *Guardar borrador* → *Publicar* lo aprobás.
2. **Actualizar un precio.** *Oferta comercial → Planes y precios* → cambiá el abono → *Guardar y aprobar*.
   El precio cambia en la tarjeta, la landing, el comparador, los datos estructurados y en las preguntas frecuentes que lo mencionan.
3. **Previsualizar y publicar.** *Estado de las webs* → el sitio muestra «cambios aprobados sin publicar» →
   *Vista previa de la web completa* → *Publicar en la web* → *Ver la web publicada (local)*.
   *Volver a la versión anterior* deshace la última publicación.

## Cómo está organizado

| Carpeta | Qué hay |
|---|---|
| `sitios/` | Sitios, líneas de GEAGRO, contacto, destino de publicación, roles y permisos, tarea de aprobación por sitio. `manage.py inicializar` |
| `contenidos/` | Páginas (encabezado, botones, SEO, secciones visibles), blog con artículos por bloques, planes y precios, funcionalidades (comparador), FAQ, testimonios, sectores, redirecciones, recursos descargables |
| `publicacion/` | Del contenido aprobado a los datos del generador, vista previa, controles, publicación con versiones, vuelta atrás y estado de cada web |
| `formularios/` | API del formulario de demo (antispam, consentimiento, aviso por email) y listado de pedidos |
| `renderer/` | Motor de sitios comerciales (copia de `GENEOS WEB/tools/sitios-comerciales`) que acepta los datos del administrador |
| `templates/`, `static/gwa/` | Pantallas propias del panel y estilo GENEOS |

### Aprobado ≠ publicado

- **Borrador**: guardado, no cambia nada.
- **Aprobado**: versión vigente dentro del administrador. Queda en la lista «pendiente de publicar».
- **En la web**: la última publicación que terminó bien. Cada publicación se genera completa, se controla
  (un solo H1 por página, títulos, precios en la home) y recién entonces reemplaza a la anterior de forma atómica.
  Si algo falla, la web queda como estaba y el error queda registrado.

En cada sitio, «Actualizar la web al aprobar cada cambio» permite publicar automáticamente al aprobar (apagado por defecto).

### Roles

Tres grupos por sitio y, en GEAGRO, también por línea: **Editor** (edita y envía a aprobación), **Publicador** (aprueba y publica)
y **Administrador** (además borra y cambia la configuración del sitio). Se asigna a las personas desde *Propiedades → Usuarios* (cada persona en el grupo que corresponda).
Cada permiso se verifica en el servidor: un editor de GEMA no ve ni puede abrir contenido de GERP, ni de otra línea.
Las cuentas de superusuario (la tuya) administran todo.

### Publicación independiente del proveedor

En *Sitios y accesos → Sitios y contacto → Publicación*:

- **Carpeta local con versiones** (por defecto): `var/publico/<sitio>/versiones/<fecha>` y el enlace `actual`.
- **Comando de despliegue**: después de generar y controlar, ejecuta un comando con `{carpeta}`. Ejemplos, cuando Infra defina:
  `npx wrangler pages deploy {carpeta} --project-name=gerp` (Cloudflare Pages) · `rsync -a --delete {carpeta}/ usuario@servidor:/var/www/gerp/`.
  Las credenciales van en variables de entorno del servidor, nunca en el repositorio ni en la web.

El formulario de demo envía a `GWA_URL_PUBLICA/api/formularios/demo/`. En local es `http://localhost:8000`; en el servidor
se configura con la URL pública del administrador y `GWA_CORS_EXTRA` con los dominios de las webs.

## GEMA: web comercial y aplicación

`https://gema.geneos.com.ar/` hoy sirve una **landing comercial estática** (título «GEMA - PLATAFORMA DE GESTIÓN DE MATAFUEGOS»,
restos de una plantilla «Softing», precio «ARS83.300 + IVA», enlaces rotos, sin login). No responde como la aplicación Django.
Queda configurado como dominio **no confirmado**: la web se genera sin URL canónica ni sitemap hasta confirmarlo.
Propuesta para validar con Infra: la web comercial en `gema.geneos.com.ar` y la aplicación en un subdominio propio
(por ejemplo `app.gema.geneos.com.ar`), sin mezclar ambos. No se modificó nada.

## Límites de la etapa 1

- La web institucional de GENEOS tiene sus páginas y su SEO cargados, pero su generador (`build.py`) se conecta en la etapa 7.
- Brochures: se suben a *Recursos descargables*; todavía no reemplazan los enlaces de las plantillas.
- Íconos y logos de los planes se indican con la ruta del archivo; la carga como imagen queda para una etapa siguiente.
- Sin segundo factor de autenticación todavía (previsto para el servidor).

## Logos y favicon

*Contenidos → Logos y favicon*: una ficha por sitio con el logo a color (encabezado), el logo blanco (portada y pie),
el favicon (PNG cuadrado de al menos 512 px; se generan todos los tamaños para navegador, iPhone, Android y accesos directos)
y un favicon SVG opcional. Las imágenes se suben a la biblioteca de Wagtail. Si un archivo no sirve (no es cuadrado,
es muy chico o no es SVG donde corresponde) el administrador lo avisa al guardar. Sigue el mismo circuito que el resto:
borrador → vista previa → aprobación → «Publicar en la web». Los campos vacíos mantienen los logos actuales.
Los íconos y logos de cada plan de GERP se eligen como imagen en la pestaña «Identidad» del plan.

## Diseño del administrador (GENEOS UI, tema oscuro)

El panel sigue la estructura de GELECTRIC (`geletric-django/core`), en tema oscuro y con la identidad de cada producto:

- **Sidebar** (`templates/gwa/ui/_sidebar.html`): arranca contraído con el isologo de GENEOS, solo íconos y el nombre en un globito.
  La hamburguesa del topbar lo fija expandido, con el logo completo, los nombres y los submenús; el estado se recuerda entre pantallas.
  En tablet y celular es un cajón que se abre y se cierra con la hamburguesa, tocando afuera o con Escape. Se arma con el menú de
  Wagtail (mismos ítems, permisos y hooks); el atajo «[» también lo expande o lo contrae.
- **Topbar** (`_topbar.html`): hamburguesa, buscador (⌘K; páginas, productos, planes, preguntas y secciones, según los permisos),
  usuario con acceso al perfil y «Cerrar sesión».
- **Componentes** (`static/gwa/ui/`): `tokens.css` (variables de GELECTRIC con la paleta oscura), `componentes.css` (sidebar,
  topbar, botones, tablas responsive, desplegables y estados de GELECTRIC con prefijo `gu-`), `wagtail.css` (los botones, campos,
  tablas y avisos de Wagtail con el mismo sistema) y `shell.js` (comportamiento del sidebar, el buscador y los desplegables).
  El tema queda oscuro aunque una cuenta tenga elegido el claro en sus preferencias.
- **Íconos**: todos lineales, de Lucide (licencia ISC en `docs/marca/lucide-LICENSE.txt`), con el trazo de GELECTRIC.
  `scripts/iconos_lucide.py` genera los SVG que reemplazan los de Wagtail (`templates/wagtailadmin/icons`) y los propios (`templates/gwa/iconos`).
- **Marca**: logos originales sin modificar en `static/gwa/marca` (GENEOS: isologotipo blanco y isologo color; GERP, GEAGRO y GEMA:
  sus isologos de `docs/marca/favicon-originales`). Los colores de cada producto son los de su isologo y están en `sitios/marca.py`:
  GERP `#1b4b8c`, GEAGRO `#0e8337`, GEMA `#ec6c05`; verde GENEOS `#128237` para acciones principales y navegación activa.
- **Tipografía**: Titillium Web servida desde el administrador (`static/gwa/ui/fuentes`, licencia OFL), sin depender de Google Fonts.

## Precios: una sola fuente

*Oferta comercial → Planes y precios* es la única pantalla de precios (la antigua «Actualizar precios», `/admin/precios/`, redirige acá).
Muestra los planes agrupados por producto, con su isologo y color, y permite editar directamente abono, implementación y vigencia;
la leyenda comercial, la moneda y el IVA están en el desplegable de cada producto. «Guardar borradores» y «Guardar y aprobar» crean
revisiones de cada plan con el historial, los permisos y la aprobación de Wagtail. El menú ⋯ de cada fila abre la edición completa
(pestañas Precio y vigencia, Presentación, Landing, Identidad y configuración), la vista previa y el historial.

Cada plan tiene como campos independientes:
abono mensual, implementación, moneda, «más IVA», leyenda de vigencia y la fecha de vigencia (interna: el inicio avisa cuando se acerca; no se publica).
Una leyenda vacía no muestra ni la nota ni el (*). «Planes y precios» muestra la fecha de la última modificación y quién la hizo, con acceso al historial de cada plan; esos datos son internos y no se publican.

Importes de origen (octubre 2026), copiados de las páginas publicadas:

| Plan | Abono | Implementación | Vigencia publicada |
|---|---|---|---|
| GERP Lite | $89.250 + IVA | $446.250 + IVA | «Los valores informados son precios vigentes hasta diciembre 2026» |
| GERP Core | $178.500 + IVA | $892.500 + IVA | ídem |
| GERP Plus | $446.250 + IVA | $1.785.000 + IVA | ídem |
| GEAGRO Lite | $89.250 + IVA | $624.750 + IVA | sin leyenda |
| GEAGRO Plus | $178.500 + IVA | $1.071.000 + IVA | sin leyenda |
| GEMA Plan mensual | $89.250 + IVA | $349.750 + IVA | «Precios válidos para octubre, noviembre y diciembre. Actualización trimestral.» |

Dónde se muestra cada precio (todo sale del plan):

- GERP: tarjetas de la home; tarjeta de cada landing (/lite/, /core/, /plus/); «otros planes» en cada landing;
  pregunta «¿Cómo es la implementación?» de cada landing; datos estructurados (Offer) de la home y las landings; nota (*).
- GEAGRO: tarjetas de la home; pregunta «¿Cuánto cuesta GEAGRO?»; datos estructurados de la home.
- GEMA: tarjeta de planes; pregunta «¿El pago es mensual y fijo?»; datos estructurados; nota (*).

En las preguntas frecuentes los importes no se escriben: se usa `[precio:clave]`, `[implementacion:clave]` o `[vigencia:clave]`
(por ejemplo `[precio:lite]`), que se reemplaza por el importe vigente con su moneda e IVA. El administrador no deja guardar
una respuesta con un importe escrito a mano ni con una clave de plan que no existe.

## Funcionalidades (comparador)

*Oferta comercial → Funcionalidades* (antes «Comparador»; mismo modelo y mismos datos) tiene una pestaña por producto con su
isologo y la cantidad cargada, y dos vistas de los mismos datos:

- **Comparador**: matriz con orden, nombre, grupo, «Resumido» (comparador resumido de la web) y una columna por cada plan real del
  producto. Cada celda es Incluido, No incluido, Opcional, Texto personalizado o «A confirmar», con ícono y texto (no solo color).
  Con un único plan (GEMA) se muestra una sola columna «Disponibilidad en …»; si se agregan planes, aparecen solos en la matriz.
- **Lista**: nombre, grupo, orden, «Visible en la web» y estado editorial.
- Filtros por grupo y estado, búsqueda por nombre, reordenar arrastrando (o con flechas) dentro de cada grupo, y menú ⋯ con
  editar, historial y vista previa. En GEAGRO cada funcionalidad puede ser de Cereales, de Vid o de ambas líneas.
- Los cambios se guardan juntos como borrador («Guardar borradores») o se aprueban («Guardar y aprobar», según el permiso) y se
  ven en la web después de «Publicar en la web». Cada funcionalidad tiene borrador, aprobación, bloqueo e historial, como los planes;
  las 16 de GERP quedaron aprobadas tal como estaban.
- La edición completa agrega descripción comercial e ícono (Lucide) —todavía no se muestran en la web—, producto y línea,
  disponibilidad por plan con su fuente y quién la validó.
- GEAGRO y GEMA no tienen funcionalidades cargadas. Sus webs todavía no muestran esta sección: cargarlas no publica nada vacío.
  Mostrarlas en esas webs requiere sumar la sección a sus plantillas.

Comparador de GERP: los valores «A confirmar» quedan en el administrador, pero en la web la celda queda vacía,
y las filas se muestran siempre, aunque todas sus celdas estén vacías (hoy: «Facturación electrónica ARCA (AFIP)»).

## Validaciones comerciales pendientes

- Valores «A confirmar» del comparador de GERP (cada valor tiene su fuente y un campo «Validado por»).
- Testimonios de INBIO HIGHWAY, KORRONTE y CELIMUNDO: siguen pendientes. Para publicar uno hay que cargar texto,
  autor, quién lo autorizó y la fecha, y marcarlo como autorizado.
- GEMA: la leyenda menciona octubre a diciembre sin año; actualizarla al cambiar el trimestre.

## Pruebas automáticas

```bash
.venv/bin/python manage.py test
```

Permisos por sitio y línea (también en el menú y el buscador), sidebar/topbar, isologos y colores oficiales, íconos lineales, borrador/aprobado/publicado de un precio, precio único en todos los lugares, moneda/IVA/vigencia, preguntas sin importes escritos, comparador sin «A confirmar», publicación fallida que no toca la web, vuelta atrás,
testimonios no autorizados y antispam del formulario.

## Documentación previa

- `docs/propuesta.html`: propuesta técnica (auditoría, arquitectura, modelo de datos, mockups, hosting, plan).
- `prototipo-publicacion/`: prototipo con el que se probó el circuito de publicación.
