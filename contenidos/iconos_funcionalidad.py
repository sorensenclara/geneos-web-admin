"""Íconos de Lucide (outline) que se pueden elegir para una funcionalidad.

Se generan con scripts/iconos_lucide.py como «icon-f-<nombre>» para mostrarlos en el administrador."""
ICONOS = [
    ("users", "Usuarios"), ("package", "Producto / inventario"), ("boxes", "Stock"), ("warehouse", "Depósito"),
    ("shopping-cart", "Compras / ventas"), ("receipt", "Comprobantes"), ("file-text", "Documento"),
    ("file-spreadsheet", "Planilla"), ("calculator", "Cálculo / contabilidad"), ("landmark", "Impuestos / organismos"),
    ("credit-card", "Pagos"), ("wallet", "Cobranzas"), ("handshake", "Clientes / CRM"), ("briefcase", "Negocio"),
    ("factory", "Producción"), ("layers", "Lotes"), ("package-check", "Entregas"), ("truck", "Logística"),
    ("chart-bar", "Reportes"), ("chart-line", "Indicadores"), ("chart-pie", "Análisis"), ("clipboard-list", "Tareas"),
    ("list-checks", "Controles"), ("calendar", "Agenda / vencimientos"), ("bell", "Avisos"), ("mail", "Correo"),
    ("message-circle", "Mensajes"), ("smartphone", "App móvil"), ("qr-code", "Código QR"), ("scan-barcode", "Código de barras"),
    ("printer", "Impresión"), ("tags", "Etiquetas / precios"), ("link", "Integraciones"), ("cloud", "En la nube"),
    ("lock", "Seguridad"), ("shield-check", "Cumplimiento"), ("badge-check", "Certificación"), ("settings", "Configuración"),
    ("wrench", "Servicio técnico"), ("wheat", "Cereales / campaña"), ("sprout", "Cultivos"), ("tractor", "Labores"),
    ("grape", "Vid"), ("leaf", "Agro"), ("droplets", "Riego / lluvias"), ("thermometer", "Clima"), ("cloud-sun", "Pronóstico"),
    ("map", "Mapa / lotes"), ("map-pin", "Ubicación"), ("flame", "Fuego"), ("fire-extinguisher", "Matafuegos"),
]
NOMBRES = [n for n, _ in ICONOS]
