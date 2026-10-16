"""Catálogo inicial de «Actualidad e ideas para publicar»: fuentes aprobadas para prueba, términos de relevancia y agenda de eventos.

Origen: investigación del 16/10/2026 (documento «GENEOS Web Admin · Documentación del proyecto»). Ninguna fuente muestra
resultados hasta pasar los controles desde el servidor donde corre el administrador (editorial.lector). Las descartadas
y las que no tienen canal automático quedan registradas con el motivo, para no volver a investigarlas.

sembrar() es idempotente: agrega lo que falta y actualiza datos de catálogo, sin tocar estado, prioridad ni resultados.
"""
from datetime import date

# Términos de relevancia por producto (sin tildes, en minúsculas; se comparan sobre el texto normalizado).
# Una publicación entra solo si menciona alguno. EXCLUIR saca ruido conocido aunque coincida.
TERMINOS = {
    "geneos": "cooperativa, cooperativas, cooperativismo, cooperativista, inaes, mutual, mutuales, economia social, economia popular, "
              "economia solidaria, facttic, cooperar, software libre, codigo abierto, open source, linux, python, django, "
              "desarrollo de software, software, programacion, programadores, ciberseguridad, datos abiertos, transformacion digital, "
              "gobierno digital, inteligencia artificial, startups tecnologicas, industria del software",
    "gerp": "arca, afip, factura electronica, facturacion, monotributo, monotributistas, iva, ganancias, ingresos brutos, retenciones, "
            "percepciones, regimen de informacion, vencimiento, vencimientos, pyme, pymes, mipyme, empresas, comercio, comercios, "
            "comerciantes, exportadores, importadores, sueldos, liquidacion de sueldos, contable, contabilidad, contadores, balance, "
            "inventario, stock, gestion empresarial, digitalizacion, erp, boletin oficial, resolucion general, cuit, emprendedores, "
            "logistica, ventas, cuenta dni, billeteras virtuales, cheques, credito pyme, laboral, empleadores",
    "geagro:cereales": "soja, maiz, trigo, girasol, sorgo, cebada, cosecha, siembra, cultivo, cultivos, granos, cereales, campana agricola, "
                       "rinde, rindes, fertilizacion, fertilizantes, agroquimicos, fitosanitarios, maquinaria agricola, productores, "
                       "bolsa de cereales, agricultura, agricola, lotes, malezas, plagas, sequia, lluvias, retenciones, inta, siembra directa",
    "geagro:vid": "vid, vinedo, vinedos, vino, vinos, bodega, bodegas, vitivinicola, vitivinicolas, vitivinicultura, uva, uvas, vendimia, "
                  "inv, coviar, malbec, enologia, enologo, poda, granizo, heladas, riego, cosecha de uva, mosto, viticultores",
    "gema": "matafuego, matafuegos, extintor, extintores, incendio, incendios, fuego, bombero, bomberos, seguridad contra incendios, "
            "proteccion contra incendios, prevencion de incendios, iram 3517, iram 3625, evacuacion, rociadores, hidrantes, detectores de humo, "
            "higiene y seguridad, riesgos del trabajo, srt, brigada, nfpa, fire, firefighter, firefighters, extinguisher, extinguishers, "
            "fire protection, fire safety, sprinkler, sprinklers, suppression",
}
EXCLUIR = {
    "geneos": "futbol, horoscopo, quiniela",
    "gerp": "dolar blue, riesgo pais, merval, bonos, futbol, horoscopo, quiniela, criptomonedas",
    "geagro": "ganaderia, hacienda, feedlot, tambo, novillos, futbol",
    "gema": "futbol, horoscopo, incendio forestal, incendios forestales, guerra, misil, bombardeo",
}
NORMATIVA = r"\b(resolucion(es)? general(es)?|resolucion \d|rg \d|decreto|ley \d|ley de|disposicion \d|norma iram|iram \d{3,5}|boletin oficial|reglamentacion|normativa)\b"

RSS_OK = "RSS público del sitio: se usan solo título, fecha, resumen breve y enlace; se respeta robots.txt."
GDELT_OK = "API gratuita; uso comercial permitido citando a The GDELT Project (gdeltproject.org/about.html). Solo últimos 3 meses."
YT_OK = "YouTube Data API v3: cuota gratuita de 10.000 unidades por día; clave guardada solo en el servidor."

# clave, producto, línea, nombre, organización, fuente_tipo, naturaleza, método, url / consulta, relación, extras
F = []


def f(clave, producto, nombre, metodo, url="", relacion="", linea="", organizacion="", fuente_tipo="medio", naturaleza="periodistica",
      consulta="", terminos="", filtrar=True, estado="prueba", prioritaria=False, motivo="", sitio_web="", tipo="noticia", condiciones=None):
    F.append(dict(clave=clave, producto=producto, linea=linea, nombre=nombre, organizacion=organizacion, fuente_tipo=fuente_tipo,
                  naturaleza=naturaleza, metodo=metodo, url=url, consulta=consulta, relacion=relacion, terminos=terminos, filtrar=filtrar,
                  estado=estado, prioritaria=prioritaria, motivo=motivo, sitio_web=sitio_web, tipo=tipo,
                  condiciones=condiciones if condiciones is not None else {"rss": RSS_OK, "gdelt": GDELT_OK, "youtube": YT_OK}.get(metodo, "")),
             )


# ---- GENEOS: cooperativismo, economía social, software libre y desarrollo tecnológico
f("geneos-facttic", "geneos", "FACTTIC · Noticias", "rss", "https://facttic.org.ar/feed/", "Federación de cooperativas de tecnología a la que pertenece GENEOS.",
  organizacion="FACTTIC", fuente_tipo="oficial", naturaleza="oficial", filtrar=False, prioritaria=True, sitio_web="https://facttic.org.ar/")
f("geneos-aciamericas", "geneos", "Cooperativas de las Américas · Noticias", "rss", "https://www.aciamericas.coop/feed/",
  "Organización regional de la Alianza Cooperativa Internacional.", organizacion="Cooperativas de las Américas", fuente_tipo="oficial",
  naturaleza="oficial", filtrar=False, sitio_web="https://www.aciamericas.coop/")
f("geneos-ica", "geneos", "Alianza Cooperativa Internacional (ICA)", "rss", "https://ica.coop/es/rss.xml", "Organismo internacional del cooperativismo.",
  organizacion="ICA", fuente_tipo="oficial", naturaleza="oficial", filtrar=False, sitio_web="https://ica.coop/es")
f("geneos-thenews-coop", "geneos", "Co-operative News", "rss", "https://www.thenews.coop/feed/", "Medio internacional especializado en cooperativas (en inglés).",
  terminos="co-op, co-ops, cooperative, cooperatives, cooperativa, cooperativas, worker, platform co-op, technology, tech, digital",
  sitio_web="https://www.thenews.coop/")
f("geneos-django", "geneos", "Django · Weblog oficial", "rss", "https://www.djangoproject.com/rss/weblog/",
  "Novedades del framework con el que se desarrolla el software de GENEOS: versiones, seguridad y comunidad.", organizacion="Django Software Foundation",
  fuente_tipo="oficial", naturaleza="oficial", filtrar=False, sitio_web="https://www.djangoproject.com/")
f("geneos-pyar-eventos", "geneos", "Python Argentina · Eventos", "rss", "https://www.python.org.ar/eventos/rss",
  "Anuncios de eventos de la comunidad Python de Argentina (PyCon AR, PyDays).", organizacion="PyAr", fuente_tipo="oficial", naturaleza="oficial",
  filtrar=False, sitio_web="https://www.python.org.ar/")
f("geneos-losandes-economia", "geneos", "Los Andes · Economía", "rss", "https://www.losandes.com.ar/rss/pages/economia.xml",
  "Se toman solo notas sobre cooperativas, mutuales y economía social.",
  terminos="cooperativa, cooperativas, cooperativismo, mutual, mutuales, economia social, economia popular, inaes, monotributo social")
f("geneos-ambito-tecnologia", "geneos", "Ámbito · Tecnología", "rss", "https://www.ambito.com/rss/pages/tecnologia.xml",
  "Desarrollo tecnológico y software en Argentina.")
f("geneos-losandes-tecno", "geneos", "Los Andes · Tecno", "rss", "https://www.losandes.com.ar/rss/pages/muy-tecno.xml", "Tecnología y software.")
f("geneos-desdelinux", "geneos", "DesdeLinux", "rss", "https://feeds.feedburner.com/desdelinuxweb", "Software libre y Linux en español.")
f("geneos-iprofesional-tecnologia", "geneos", "iProfesional · Tecnología", "rss", "https://www.iprofesional.com/rss/tecnologia",
  "Tecnología y transformación digital en Argentina.")
f("geneos-gdelt", "geneos", "GDELT · cooperativismo y tecnología en Argentina", "gdelt", relacion="Búsqueda en medios argentinos: cooperativas, INAES, economía social y software libre.",
  fuente_tipo="gdelt", consulta='(cooperativas OR cooperativismo OR INAES OR "economía social" OR "software libre")', sitio_web="https://www.gdeltproject.org/")
f("geneos-inaes", "geneos", "INAES · Noticias", "ninguno", relacion="Organismo que regula a las cooperativas.", organizacion="INAES", fuente_tipo="oficial",
  naturaleza="oficial", estado="sin_canal", prioritaria=True, sitio_web="https://www.argentina.gob.ar/capital-humano/inaes/noticias",
  motivo="No publica RSS ni API. Usar «Cargar novedad oficial» con el enlace de la noticia o resolución.", condiciones="")
f("geneos-tiempoar", "geneos", "Tiempo Argentino", "rss", "https://www.tiempoar.com.ar/feed/", "Diario editado por una cooperativa.", estado="descartada",
  motivo="El feed devuelve contenido ajeno al diario (publicaciones de casinos de 2025).")
f("geneos-muylinux", "geneos", "MuyLinux", "rss", "https://www.muylinux.com/feed/", "Software libre.", estado="descartada",
  motivo="Su robots.txt no permite la lectura automática.")

# ---- GERP: pymes, gestión empresarial, ARCA, comercio y digitalización
f("gerp-arca-youtube", "gerp", "ARCA · canal oficial de YouTube", "youtube", relacion="Comunicados y explicaciones oficiales de ARCA sobre impuestos y facturación.",
  organizacion="ARCA", fuente_tipo="oficial", naturaleza="oficial", consulta="UCe0zC5Uf5U1YDDMF3_W-97A", filtrar=False, prioritaria=True,
  sitio_web="https://www.youtube.com/@ARCA_informa")
f("gerp-ambito-fiscales", "gerp", "Ámbito · Novedades Fiscales", "rss", "https://www.ambito.com/rss/pages/novedades-fiscales.xml",
  "Cambios impositivos, vencimientos y resoluciones de ARCA explicados por un medio.")
f("gerp-ambito-economia", "gerp", "Ámbito · Economía", "rss", "https://www.ambito.com/rss/pages/economia.xml", "Economía de pymes y comercio.")
f("gerp-ambito-negocios", "gerp", "Ámbito · Negocios", "rss", "https://www.ambito.com/rss/pages/negocios.xml", "Empresas, comercio y gestión.")
f("gerp-iprofesional-impuestos", "gerp", "iProfesional · Impuestos", "rss", "https://www.iprofesional.com/rss/impuestos", "Impuestos y novedades de ARCA.")
f("gerp-iprofesional-legales", "gerp", "iProfesional · Legales", "rss", "https://www.iprofesional.com/rss/legales", "Normativa que afecta a empresas.")
f("gerp-iprofesional-management", "gerp", "iProfesional · Management", "rss", "https://www.iprofesional.com/rss/management", "Gestión empresarial.")
f("gerp-gdelt", "gerp", "GDELT · pymes, ARCA y facturación en Argentina", "gdelt", relacion="Búsqueda en medios argentinos: ARCA, monotributo, facturación electrónica y pymes.",
  fuente_tipo="gdelt", consulta='(ARCA OR monotributo OR "factura electrónica" OR "facturación electrónica" OR pymes OR "ingresos brutos")',
  sitio_web="https://www.gdeltproject.org/")
f("gerp-arca", "gerp", "ARCA · Novedades", "ninguno", relacion="Organismo de recaudación: facturación, regímenes y vencimientos.", organizacion="ARCA",
  fuente_tipo="oficial", naturaleza="oficial", estado="sin_canal", prioritaria=True, sitio_web="https://www.arca.gob.ar/",
  motivo="No publica RSS ni API. Se cubre con su canal de YouTube, GDELT y «Cargar novedad oficial».", condiciones="")
f("gerp-boletin-oficial", "gerp", "Boletín Oficial", "ninguno", relacion="Publicación oficial de leyes, decretos y resoluciones.",
  organizacion="Boletín Oficial de la República Argentina", fuente_tipo="oficial", naturaleza="oficial", estado="sin_canal",
  sitio_web="https://www.boletinoficial.gob.ar/", motivo="Sin RSS ni API documentada; leerlo exigiría scraping. Usar «Cargar novedad oficial».", condiciones="")
f("gerp-cronista", "gerp", "El Cronista · Economía", "rss", "https://www.cronista.com/files/rss/economia.xml", "Economía.", estado="descartada",
  motivo="Su robots.txt no permite la lectura automática de los feeds.")
f("gerp-ambito-finanzas", "gerp", "Ámbito · Finanzas", "rss", "https://www.ambito.com/rss/pages/finanzas.xml", "Finanzas.", estado="descartada",
  motivo="Casi todo es cotización del dólar: poco relacionado con GERP.")
f("gerp-bcra", "gerp", "BCRA · API de estadísticas", "ninguno", relacion="Datos de contexto (cotizaciones).", organizacion="BCRA", fuente_tipo="oficial",
  estado="descartada", motivo="Son datos, no novedades; el aviso legal pide permiso previo para uso comercial.", condiciones="")

# ---- GEMA: matafuegos, extintores y seguridad contra incendios
f("gema-iram", "gema", "IRAM · Novedades institucionales", "rss", "https://www.iram.org.ar/novedades/category/institucional/feed/",
  "Instituto que emite las normas IRAM de extintores (3517, 3625…).", organizacion="IRAM", fuente_tipo="oficial", naturaleza="oficial", prioritaria=True,
  terminos="incendio, incendios, extintor, extintores, matafuego, matafuegos, fuego, seguridad, 3517, 3625, bombero, bomberos, proteccion",
  sitio_web="https://www.iram.org.ar/")
f("gema-iram-general", "gema", "IRAM · Todas las novedades", "rss", "https://www.iram.org.ar/novedades/feed/",
  "Instituto que emite las normas IRAM de extintores.", organizacion="IRAM", fuente_tipo="oficial", naturaleza="oficial", prioritaria=True,
  terminos="incendio, incendios, extintor, extintores, matafuego, matafuegos, fuego, seguridad, 3517, 3625, bombero, bomberos, proteccion",
  sitio_web="https://www.iram.org.ar/")
f("gema-bomberos", "gema", "Bomberos Voluntarios de Argentina", "rss", "https://www.bomberosra.org.ar/feed/",
  "Consejo Nacional de Federaciones de Bomberos Voluntarios: prevención, capacitación y normativa.", organizacion="Consejo Nacional de Bomberos Voluntarios",
  fuente_tipo="oficial", naturaleza="oficial", sitio_web="https://www.bomberosra.org.ar/")
f("gema-fsja", "gema", "Fire & Safety Journal Americas", "rss", "https://fireandsafetyjournalamericas.com/feed/",
  "Revista de protección contra incendios para América (en inglés).", sitio_web="https://fireandsafetyjournalamericas.com/")
f("gema-nfpa-podcast", "gema", "NFPA · Podcast oficial", "rss", "https://rss.libsyn.com/shows/18452/destinations/12612.xml",
  "Asociación internacional que publica códigos de protección contra incendios (en inglés).", organizacion="NFPA", fuente_tipo="oficial",
  naturaleza="oficial", filtrar=False, sitio_web="https://www.nfpa.org/")
f("gema-redproteger", "gema", "Red Proteger · Safety Blog", "rss", "https://redproteger.com.ar/safetyblog/feed/",
  "Blog argentino de seguridad laboral y protección contra incendios.", sitio_web="https://redproteger.com.ar/")
f("gema-iram-youtube", "gema", "IRAM · canal oficial de YouTube", "youtube", relacion="Videos oficiales sobre normas y certificación.",
  organizacion="IRAM", fuente_tipo="oficial", naturaleza="oficial", consulta="UC6kPFpdaIzmC5nh4XHD00Rg",
  terminos="incendio, incendios, extintor, extintores, matafuego, matafuegos, fuego, seguridad, 3517, 3625, bombero, bomberos")
f("gema-bomberos-youtube", "gema", "Bomberos Voluntarios · canal oficial de YouTube", "youtube", relacion="Videos oficiales de prevención y capacitación.",
  organizacion="Consejo Nacional de Bomberos Voluntarios", fuente_tipo="oficial", naturaleza="oficial", consulta="UCFaupvbQ4EsgQE3NjM6VcBg")
f("gema-gdelt", "gema", "GDELT · matafuegos y extintores en Argentina", "gdelt", relacion="Búsqueda en medios argentinos sobre matafuegos, extintores y prevención de incendios.",
  fuente_tipo="gdelt", consulta='(matafuegos OR matafuego OR extintores OR "seguridad contra incendios" OR "prevención de incendios")',
  sitio_web="https://www.gdeltproject.org/")
f("gema-srt", "gema", "Superintendencia de Riesgos del Trabajo", "ninguno", relacion="Normativa de higiene y seguridad laboral.", organizacion="SRT",
  fuente_tipo="oficial", naturaleza="oficial", estado="sin_canal", sitio_web="https://www.argentina.gob.ar/srt",
  motivo="Sin RSS ni API. Usar «Cargar novedad oficial».", condiciones="")
f("gema-editores", "gema", "Editores SRL (Ingeniería Eléctrica)", "rss", "https://www.editores-srl.com.ar/rss.xml", "Revista técnica.", estado="descartada",
  motivo="Sin publicaciones desde 2019.")

# ---- GEAGRO: cereales y vid
f("geagro-bichos", "geagro", "Bichos de Campo", "rss", "https://bichosdecampo.com/feed/", "Periodismo agropecuario argentino.")
f("geagro-bichos-vid", "geagro", "Bichos de Campo · Vitivinicultura", "rss", "https://bichosdecampo.com/tag/vitivinicultura/feed/", "Vitivinicultura.", linea="vid")
f("geagro-infocampo", "geagro", "Infocampo", "rss", "https://www.infocampo.com.ar/feed/", "Noticias del agro argentino.")
f("geagro-infocampo-agricultura", "geagro", "Infocampo · Agricultura", "rss", "https://www.infocampo.com.ar/category/agricultura/feed/", "Agricultura extensiva.",
  linea="cereales")
f("geagro-infocampo-vid", "geagro", "Infocampo · Vitivinicultura", "rss", "https://www.infocampo.com.ar/category/vitivinicultura/feed/", "Vitivinicultura.",
  linea="vid")
f("geagro-expoagro", "geagro", "Expoagro · Noticias", "rss", "https://www.expoagro.com.ar/feed/", "Muestra agroindustrial: novedades del sector.",
  organizacion="Expoagro", sitio_web="https://www.expoagro.com.ar/")
f("geagro-defrente", "geagro", "De Frente al Campo · Agro Noticias", "rss", "https://www.defrentealcampo.com.ar/categoria/agro-noticias/feed/", "Agro.")
f("geagro-losandes-fincas", "geagro", "Los Andes · AgroIndustria", "rss", "https://www.losandes.com.ar/rss/pages/fincas.xml", "Agro de Cuyo: viñedos y fincas.")
f("geagro-losandes-cuyo", "geagro", "Los Andes · Cuyo Agro", "rss", "https://www.losandes.com.ar/rss/pages/Cuyo%20Agro.xml", "Agro de Cuyo.")
f("geagro-iprofesional-vinos", "geagro", "iProfesional · Vinos y Bodegas", "rss", "https://www.iprofesional.com/rss/vinos", "Vinos y bodegas.", linea="vid")
f("geagro-inta", "geagro", "INTA Informa", "rss", "https://intainforma.inta.gob.ar/feed/", "Instituto Nacional de Tecnología Agropecuaria.",
  organizacion="INTA", fuente_tipo="oficial", naturaleza="oficial", prioritaria=True)
f("geagro-expoagro-youtube", "geagro", "Expoagro · canal de YouTube", "youtube", relacion="Videos de la muestra y del sector.", organizacion="Expoagro",
  fuente_tipo="oficial", naturaleza="oficial", consulta="UCL7FxmRKzatPxn4YIYNuN6Q", linea="cereales")
f("geagro-bolsa-youtube", "geagro", "Bolsa de Cereales · canal de YouTube", "youtube", relacion="Estimaciones y análisis de la Bolsa de Cereales.",
  organizacion="Bolsa de Cereales de Buenos Aires", fuente_tipo="oficial", naturaleza="oficial", consulta="UCbhKr6_D_xPxK5kZmkH1aGQ", linea="cereales")
f("geagro-gdelt-cereales", "geagro", "GDELT · agricultura y cereales en Argentina", "gdelt", relacion="Búsqueda en medios argentinos sobre siembra, cosecha y campaña agrícola.",
  fuente_tipo="gdelt", linea="cereales", consulta='(siembra OR cosecha OR "campaña agrícola" OR "Bolsa de Cereales" OR soja OR trigo)',
  sitio_web="https://www.gdeltproject.org/")
f("geagro-gdelt-vid", "geagro", "GDELT · vitivinicultura en Argentina", "gdelt", relacion="Búsqueda en medios argentinos sobre viñedos, vendimia y bodegas.",
  fuente_tipo="gdelt", linea="vid", consulta='(vitivinicultura OR viñedos OR vendimia OR bodegas OR "Instituto Nacional de Vitivinicultura")',
  sitio_web="https://www.gdeltproject.org/")
f("geagro-supercampo", "geagro", "Supercampo (Perfil)", "rss", "https://supercampo.perfil.com/feed/", "Agro.", estado="descartada", motivo="Sin publicaciones desde 2019.")
f("geagro-areadelvino", "geagro", "Área del Vino", "rss", "", "Vitivinicultura.", estado="descartada", motivo="Sitio en construcción (16/10/2026).")

# ---- Todos los productos
f("todos-trends", "todos", "Google Trends · Tendencias del día en Argentina", "trends", "https://trends.google.com/trending/rss?geo=AR",
  "Búsquedas en aumento en Argentina; solo se toman las relacionadas con cada producto.", fuente_tipo="trends", naturaleza="tendencia", tipo="tendencia",
  condiciones="Exportación RSS ofrecida por Google Trends; citar «Fuente: Google Trends».", sitio_web="https://trends.google.com/trending?geo=AR")
f("todos-google-news", "todos", "Google News RSS", "google_news", "https://news.google.com/rss/search?hl=es-419&gl=AR&ceid=AR:es-419",
  "Búsqueda de noticias por tema.", estado="experimental",
  motivo="Sin documentación oficial; los términos de Google prohíben el acceso automatizado. No se usa salvo prueba interna autorizada.", condiciones="")

FUENTES = F

# Agenda inicial. Próximos: solo con fecha confirmada por el organizador o un organismo. El resto: «Por confirmar».
EVENTOS = [
    dict(clave="evento:expoagro-2027", sitio="geagro", titulo="Expoagro 2027", inicio=date(2027, 3, 9), fin=date(2027, 3, 12),
         lugar="San Nicolás, Buenos Aires (km 225, RN 9)", modalidad="Presencial", organizador="Exponenciar S.A.",
         url="https://www.expoagro.com.ar/visit-expoagro", confirmada=True, fecha_fuente="Sitio oficial de Expoagro",
         relacion="Muestra agroindustrial más grande del país: productores y contratistas de cereales."),
    dict(clave="evento:agroactiva-2027", sitio="geagro", titulo="AgroActiva 2027", inicio=date(2027, 6, 2), fin=date(2027, 6, 5),
         lugar="Armstrong, Santa Fe", modalidad="Presencial", organizador="AgroActiva", url="https://agroactiva.com/", confirmada=False,
         fecha_fuente="Según prensa (Noticias de Campo, 07/09/2026); el sitio oficial todavía muestra 2026",
         relacion="Muestra agroindustrial del centro del país."),
    dict(clave="evento:vendimia-2027", sitio="geagro", linea="vid", titulo="Fiesta Nacional de la Vendimia 2027 · Acto central", inicio=date(2027, 3, 6),
         fin=date(2027, 3, 6), lugar="Teatro Griego Frank Romero Day, Mendoza", modalidad="Presencial", organizador="Gobierno de Mendoza",
         url="https://www.mendoza.gov.ar/", confirmada=False, fecha_fuente="Según prensa (El Sol, 15/08/2026)",
         relacion="Celebración de la cosecha de uva: agenda vitivinícola de Mendoza."),
    dict(clave="evento:coop-rionegro-2026", sitio="geneos", titulo="56° Congreso de Cooperativas de Río Negro", inicio=date(2026, 11, 14), fin=date(2026, 11, 15),
         lugar="San Carlos de Bariloche, Río Negro", modalidad="Presencial", organizador="FECORN y Gobierno de Río Negro, con INAES",
         url="https://rionegro.gov.ar/articulo/59783/las-cooperativas-rionegrinas-tendran-su-congreso-en-bariloche", confirmada=True,
         fecha_fuente="Comunicado oficial del Gobierno de Río Negro (18/06/2026)", relacion="Congreso cooperativo con participación de INAES."),
    dict(clave="evento:coopsday-2027", sitio="geneos", titulo="Día Internacional de las Cooperativas 2027", inicio=date(2027, 7, 3), fin=date(2027, 7, 3),
         lugar="Todo el mundo", modalidad="Celebración", organizador="Alianza Cooperativa Internacional y ONU (COPAC)", url="https://www.coopsday.coop/",
         confirmada=True, fecha_fuente="Regla oficial: primer sábado de julio (coopsday.coop)", relacion="Fecha central del movimiento cooperativo."),
    dict(clave="evento:nerdearla-mexico-2026", sitio="geneos", titulo="Nerdearla México 2026", inicio=date(2026, 11, 18), fin=date(2026, 11, 21),
         lugar="ExpoReforma, Ciudad de México (México)", modalidad="Presencial y transmisión en vivo", organizador="Nerdearla",
         url="https://nerdearla.com/en/mexico/", confirmada=True, fecha_fuente="Sitio oficial de Nerdearla",
         relacion="Conferencia de tecnología y software libre creada en Argentina (edición fuera del país)."),
    dict(clave="evento:congregacoop-2026", sitio="geneos", titulo="CongregaCoop 2026 · Congreso Internacional de Cooperativismo", inicio=date(2026, 10, 28),
         fin=date(2026, 10, 29), lugar="Universidad Siglo 21, Córdoba", modalidad="Presencial", organizador="FECOFE y cooperativas brasileñas",
         url="https://congregacoop.com/", confirmada=False, fecha_fuente="Según prensa (COLSECOR Noticias, 30/07/2026); el sitio oficial no muestra la fecha",
         relacion="Congreso internacional de cooperativismo en Argentina."),
    dict(clave="evento:nerdearla-ar-2027", sitio="geneos", titulo="Nerdearla Argentina 2027", inicio=None, fin=None, lugar="Buenos Aires", modalidad="",
         organizador="Nerdearla", url="https://nerdearla.com/en/editions", confirmada=False,
         fecha_fuente="Edición anunciada sin fechas; la de 2026 fue del 22 al 26/09", relacion="Conferencia de tecnología y software libre."),
    dict(clave="evento:flisol-2027", sitio="geneos", titulo="FLISoL 2027", inicio=None, fin=None, lugar="Sedes en todo el país", modalidad="Presencial",
         organizador="Comunidades de software libre (flisol.info)", url="https://flisol.info/", confirmada=False,
         fecha_fuente="Sin anuncio; suele ser el cuarto sábado de abril (24/04/2027)", relacion="Festival latinoamericano de instalación de software libre."),
    dict(clave="evento:pyconar", sitio="geneos", titulo="PyCon Argentina", inicio=None, fin=None, lugar="", modalidad="", organizador="Python Argentina (PyAr)",
         url="https://www.python.org.ar/", confirmada=False, fecha_fuente="python.org.ar no tiene eventos futuros publicados",
         relacion="Conferencia de Python, lenguaje con el que se desarrolla el software de GENEOS."),
    dict(clave="evento:biel-2027", sitio="gema", titulo="BIEL Light + Building Buenos Aires 2027", inicio=date(2027, 10, 20), fin=date(2027, 10, 23),
         lugar="La Rural, Buenos Aires", modalidad="Presencial", organizador="Messe Frankfurt Argentina",
         url="https://biel-light-building.ar.messefrankfurt.com/buenosaires/en.html", confirmada=False,
         fecha_fuente="Solo en un sitio de terceros; confirmar en el sitio oficial", relacion="Feria de la industria eléctrica y de instalaciones."),
    dict(clave="evento:intersec-ba-2028", sitio="gema", titulo="Intersec Buenos Aires 2028", inicio=None, fin=None, lugar="La Rural, Buenos Aires",
         modalidad="Presencial", organizador="Messe Frankfurt Argentina", url="https://intersec-buenosaires.ar.messefrankfurt.com/", confirmada=False,
         fecha_fuente="Feria bienal: la última fue del 2 al 4/09/2026", relacion="Principal feria de seguridad y protección contra incendios del país."),
]


def sembrar(FuenteActualidad=None, IdeaEditorial=None, SitioWeb=None, LineaProducto=None):
    """Carga o actualiza el catálogo. Acepta los modelos históricos de una migración."""
    from django.utils import timezone
    if FuenteActualidad is None:
        from sitios.models import LineaProducto, SitioWeb
        from .models import FuenteActualidad, IdeaEditorial
    for orden, d in enumerate(FUENTES):
        d = dict(d)
        estado, prioritaria, motivo = d.pop("estado"), d.pop("prioritaria"), d.pop("motivo")
        obj, nueva = FuenteActualidad.objects.get_or_create(clave=d["clave"], defaults=dict(d, estado=estado, prioritaria=prioritaria,
                                                                                           motivo=motivo, orden=orden))
        if not nueva:  # solo datos de catálogo: estado, prioridad, términos y resultados se administran desde el blog
            for k in ("producto", "linea", "nombre", "organizacion", "fuente_tipo", "naturaleza", "tipo", "metodo", "url", "consulta",
                      "relacion", "condiciones", "sitio_web"):
                setattr(obj, k, d[k])
            if estado in ("descartada", "sin_canal", "experimental") and obj.estado == "prueba":
                obj.estado, obj.motivo = estado, motivo
            obj.orden = orden
            obj.save()
    hoy = timezone.localdate()
    sitios = {s.clave: s for s in SitioWeb.objects.all()}
    for e in EVENTOS:
        sitio = sitios.get(e["sitio"])
        if sitio is None:
            continue
        linea = LineaProducto.objects.filter(sitio=sitio, clave=e.get("linea", "")).first() if e.get("linea") else None
        datos = dict(linea=linea, tipo="evento", fuente_tipo="evento", naturaleza="evento", titulo=e["titulo"], fuente=e["organizador"][:120],
                     fuente_url=e["url"], evento_fecha=e["inicio"], evento_fin=e["fin"], evento_lugar=e["lugar"][:120], modalidad=e["modalidad"][:20],
                     organizador=e["organizador"][:120], fecha_confirmada=e["confirmada"], fecha_fuente=e["fecha_fuente"][:160],
                     relacion=e["relacion"][:300], descripcion=e["relacion"], propuesta=f"{e['titulo']}: qué esperar y cómo prepararse"[:200])
        obj = IdeaEditorial.objects.filter(sitio=sitio, clave=e["clave"]).first()
        if obj is None:
            IdeaEditorial.objects.create(sitio=sitio, clave=e["clave"], consultado=hoy, **datos)
        else:
            for k, v in datos.items():
                setattr(obj, k, v)
            obj.save()
