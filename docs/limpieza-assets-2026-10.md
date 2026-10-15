# Limpieza y optimización de assets · octubre 2026

Rama `limpieza-assets` en GENEOS WEB y commit en `etapa-1` del administrador. Todo es reversible con Git.

## Método

- Se generaron completas la web institucional (`build.py`) y las tres webs comerciales (con el contenido real del administrador) y se registró cada archivo que usan: HTML, CSS (`url()`), JS, manifest, datos SEO y los recursos que copia el generador (`GWA_LISTA_RECURSOS`).
- Un archivo se borró solo si no aparece en ninguna web generada ni por nombre en plantillas, CSS, JS, scripts ni datos del administrador.
- Optimización solo sin pérdida visible: SVG con svgo comparando el render antes/después; PNG sin pérdida (oxipng, píxeles idénticos); JPG/WebP solo si ahorra más del 15 % con PSNR ≥ 40 dB.
- Verificación: 0 recursos faltantes en las 4 webs y comparación visual de 21 páginas en escritorio y celular.

## Favicons nuevos

| Proyecto | Ubicación | Archivos |
|---|---|---|
| GERP | `renderer/favicons/gerp/` | favicon.ico, favicon.svg, 16/32 px, apple-touch-icon, android 192/512, site.webmanifest |
| GEAGRO | `renderer/favicons/geagro/` | favicon.ico, favicon.svg, 16/32 px, apple-touch-icon, android 192/512, site.webmanifest |
| GEMA | `renderer/favicons/gema/` | favicon.ico, favicon.svg, 16/32 px, apple-touch-icon, android 192/512, site.webmanifest |
| GENEOS Web Admin | `static/gwa/favicon/` | ídem; el panel de Wagtail ya no usa el favicon de Wagtail |

Los archivos de origen (`favicon_io (…)`, `*-favicon.svg` e `img/recursos/geneos-isotipo-favicon-admin.svg`) se movieron de GENEOS WEB al administrador; los PNG se optimizaron sin pérdida.

## Archivos eliminados de GENEOS WEB (36, también de `public/`)

- `geagro-landing/icons/brand/GENEOS.svg`
- `geagro-landing/icons/brand/geneos-logo.png`
- `geagro-landing/icons/brand/logo-geagro.svg`
- `geagro-landing/images/backgrounds/bg-cta-cereales.webp`
- `geagro-landing/images/backgrounds/bg-cta-vid.webp`
- `geagro-landing/images/backgrounds/bg-geneos.jpg`
- `geagro-landing/images/cereales/campo-bg.jpg`
- `geagro-landing/images/shared/cta-productor.jpg`
- `geagro-landing/images/shared/hero.jpg`
- `geagro-landing/images/vid/vid-bg.jpg`
- `img/2023/11/background-gestion-01.webp`
- `img/2024/03/Coletio-de-Profesionales-de-Trabajo-Social-Santa-Fe.webp`
- `img/2024/03/EL-LOGRO.webp`
- `img/2024/03/Rompecabezas-Coop-de-Contenidos.webp`
- `img/2024/04/1.svg`
- `img/2024/04/2-1.svg`
- `img/2024/04/3.svg`
- `img/2024/04/5-1024x637.webp`
- `img/2024/04/700x800.webp`
- `img/2024/10/6.svg`
- `img/2025/03/Imagenes-GERP-WEB-01.svg`
- `img/2025/03/Imagenes-GERP-WEB-02.svg`
- `img/2025/03/Imagenes-GERP-WEB-03.svg`
- `img/elementor/thumbs/1-rh26dypjooggcth84gjk78imc3z8munprbvmytv63k.webp`
- `img/elementor/thumbs/2-rh26e1j296kbbnd4nzrfwpt049lc9xywrpu3enqzkw.webp`
- `img/elementor/thumbs/3-rh26e4cktoo6ah917izbm73dwf7fx1a3s3sjuhmt28.webp`
- `img/elementor/thumbs/4-rh26e91rruulwj27g30ggnwovck9zisrgr1z8vfu74.webp`
- `img/elementor/thumbs/5-rh26ect4j6zr6ywqu4myqmyj8w1qub7ot9nx5za9i8.webp`
- `img/elementor/thumbs/WhatsApp-Image-2023-10-17-at-07.55.08-1-qehlinwioool2rva2remaunn8jv8yc6htse0m5opsw.webp`
- `img/elementor/thumbs/WhatsApp-Image-2023-10-17-at-07.55.08-2-qehlimyohunar5wn88zzqcw6n5zvqn2rhnqj4vq3z4.webp`
- `img/elementor/thumbs/photo1698244568-4-qehlgv1nl47stohhlhdd0t0u8yqx7810kvdii2cvq8.webp`
- `img/elementor/thumbs/photo1698245973-3-qehlh0ooq4firc9aojt4frllt9z4henelnafdq4iow.webp`
- `img/geagro/Isologo-geagro-cereales.svg`
- `img/geagro/Isologo-geagro-vid.svg`
- `img/hero/hero-geneos-final.webp`
- `img/og-geneos.webp`

## Optimizados (77)

| Archivo | Antes | Después |
|---|---:|---:|
| `assets/img/2024/12/Manual-de-Marca-GENEOS.svg` | 349.4 KB | 152.1 KB |
| `assets/geagro-landing/icons/proceso/vid-paso-planifica.svg` | 24.9 KB | 11.3 KB |
| `assets/geagro-landing/images/vid/panel-vid.jpg` | 76.8 KB | 64.2 KB |
| `assets/geagro-landing/images/cereales/panel-campo.jpg` | 53.2 KB | 44.6 KB |
| `assets/geagro-landing/icons/proceso/vid-paso-alerta.svg` | 15.6 KB | 7.0 KB |
| `assets/img/recursos/geneos-isologotipo.svg` | 25.4 KB | 17.4 KB |
| `assets/img/2023/10/Geneos-mundo.svg` | 23.5 KB | 17.1 KB |
| `assets/geagro-landing/icons/proceso/vid-paso-clima.svg` | 11.2 KB | 4.9 KB |
| `assets/geagro-landing/icons/vid/vid-clima.svg` | 11.2 KB | 4.9 KB |
| `assets/img/geagro/logo-geagro.svg` | 21.0 KB | 15.5 KB |
| `assets/img/productos/geagro.svg` | 21.0 KB | 15.5 KB |
| `assets/geagro-landing/icons/proceso/campo-acopio-propio.svg` | 6.8 KB | 2.6 KB |
| `assets/geagro-landing/icons/proceso/campo-paso-planifica.svg` | 6.9 KB | 3.1 KB |
| `assets/geagro-landing/icons/shared/plan-tecnico.svg` | 6.9 KB | 3.1 KB |
| `assets/geagro-landing/icons/proceso/campo-paso-compra.svg` | 6.6 KB | 2.8 KB |
| `assets/gerp/img/sectores/laboratorios.svg` | 15.1 KB | 11.5 KB |
| `assets/img/favicon-192.png` | 17.9 KB | 14.4 KB |
| `assets/gerp/img/sectores/retail.svg` | 11.5 KB | 8.3 KB |
| `assets/img/favicon-180.png` | 16.3 KB | 13.2 KB |
| `assets/img/recursos/geneos-isologotipo-blanco.svg` | 12.6 KB | 9.5 KB |
| `assets/geagro-landing/icons/proceso/campo-paso-ejecucion.svg` | 5.2 KB | 2.4 KB |
| `assets/img/productos/gema-logo-blanco.svg` | 10.2 KB | 7.5 KB |
| `assets/img/productos/gema.svg` | 10.2 KB | 7.5 KB |
| `assets/img/2025/02/Isologo-GERP-Full.svg` | 11.6 KB | 9.0 KB |
| `assets/img/productos/gerp.svg` | 11.6 KB | 9.0 KB |
| `assets/geagro-landing/icons/proceso/vid-paso-gestiona.svg` | 4.7 KB | 2.2 KB |
| `assets/geagro-landing/icons/proceso/campo-paso-asigna.svg` | 4.7 KB | 2.1 KB |
| `assets/img/recursos/geneos-isotipo.svg` | 7.2 KB | 4.8 KB |
| `assets/img/recursos/geneos-isologotipo-negro.svg` | 11.8 KB | 9.5 KB |
| `assets/geagro-landing/icons/vid/vid-plan-tecnico.svg` | 10.4 KB | 8.4 KB |
| `assets/geagro-landing/icons/nosotros/equipo.png` | 10.0 KB | 7.9 KB |
| `assets/img/geagro/logo-geagro-white.svg` | 9.6 KB | 7.6 KB |
| `assets/img/recursos/gema-logotipo.svg` | 11.2 KB | 9.3 KB |
| `assets/img/productos/gerp-logo-blanco.svg` | 9.4 KB | 7.7 KB |
| `assets/geagro-landing/icons/nosotros/software-libre.png` | 12.0 KB | 10.4 KB |
| `assets/gerp/img/gerp-planes/gerp-lite-logo-blanco.svg` | 4.1 KB | 2.8 KB |
| `assets/gerp/img/sectores/manufactureros.svg` | 7.3 KB | 6.1 KB |
| `assets/geagro-landing/icons/proceso/campo-paso-analisis.svg` | 2.3 KB | 1.0 KB |
| `assets/geagro-landing/icons/vid/vid-insumos.svg` | 5.0 KB | 3.9 KB |
| `assets/gerp/img/gerp-planes/gerp-core-logo-blanco.svg` | 4.7 KB | 3.6 KB |
| `assets/geagro-landing/icons/nosotros/10-anios.png` | 9.2 KB | 8.0 KB |
| `assets/gerp/img/gerp-planes/gerp-plus-logo-blanco.svg` | 4.6 KB | 3.5 KB |
| `assets/img/2023/10/Icon_moodle.svg` | 3.1 KB | 2.1 KB |
| `assets/geagro-landing/icons/cereales/campo-plan-tecnico.svg` | 3.2 KB | 2.3 KB |
| `assets/img/2024/11/G-ERP-Lite.svg` | 8.2 KB | 7.3 KB |
| `assets/geagro-landing/icons/brand/isologo-geagro.svg` | 3.6 KB | 2.8 KB |
| `assets/geagro-landing/icons/vid/vid-control.svg` | 4.0 KB | 3.2 KB |
| `assets/img/2024/11/G-ERP-Core.svg` | 10.5 KB | 9.7 KB |
| `assets/img/geagro/Isologo-geagro.svg` | 3.6 KB | 2.8 KB |
| `assets/geagro-landing/icons/vid/vid-operaciones.svg` | 4.0 KB | 3.2 KB |
| `assets/img/2024/11/G-ERP-Plus.svg` | 5.6 KB | 4.8 KB |
| `assets/GERP.svg` | 4.8 KB | 4.0 KB |
| `assets/geagro-landing/icons/cereales/campo-acopio.svg` | 3.5 KB | 2.8 KB |
| `assets/GEAGRO.svg` | 3.5 KB | 2.9 KB |
| `assets/geagro-landing/icons/vid/vid-compras.svg` | 2.5 KB | 1.9 KB |
| `assets/geagro-landing/icons/shared/clima.svg` | 1.2 KB | 0.6 KB |
| `assets/geagro-landing/icons/cereales/campo-transporte.svg` | 2.7 KB | 2.2 KB |
| `assets/GEMA.svg` | 3.1 KB | 2.6 KB |
| `assets/geagro-landing/icons/cereales/campo-insumos.svg` | 3.4 KB | 2.8 KB |
| `assets/geagro-landing/icons/vid/vid-graficos.svg` | 2.4 KB | 1.9 KB |
| `assets/geagro-landing/icons/vid/vid-campo.svg` | 3.8 KB | 3.3 KB |
| `assets/geagro-landing/icons/cereales/campo-control.svg` | 3.1 KB | 2.6 KB |
| `assets/geagro-landing/icons/brand/isologo-vid.svg` | 2.9 KB | 2.4 KB |
| `assets/geagro-landing/icons/brand/isologo-campo.svg` | 3.2 KB | 2.7 KB |
| `assets/img/2023/10/nodejs_b.svg` | 2.0 KB | 1.6 KB |
| `assets/img/recursos/geneos-isotipo-favicon-admin.svg` | 2.5 KB | 2.1 KB |
| `assets/gerp/img/sectores/mayoristas.svg` | 3.4 KB | 3.0 KB |
| `assets/geagro-landing/icons/cereales/campo-campo.svg` | 3.0 KB | 2.6 KB |
| `assets/img/2023/10/angularjs_b.svg` | 0.7 KB | 0.4 KB |
| `assets/img/2023/10/django_b.svg` | 0.7 KB | 0.4 KB |
| `assets/img/2023/10/moodle_b.svg` | 1.2 KB | 1.0 KB |
| `assets/geagro-landing/icons/cereales/campo-compras.svg` | 1.5 KB | 1.3 KB |
| `assets/geagro-landing/icons/cereales/campo-operaciones.svg` | 2.6 KB | 2.3 KB |
| `assets/img/2023/10/reactjs_b.svg` | 1.3 KB | 1.1 KB |
| `assets/geagro-landing/icons/cereales/campo-graficos.svg` | 1.5 KB | 1.3 KB |
| `assets/img/2023/10/Vuejs_b.svg` | 0.5 KB | 0.3 KB |
| `assets/img/favicon-32.png` | 1.7 KB | 1.6 KB |
