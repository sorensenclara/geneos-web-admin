/* Formulario de demo conectado a GENEOS Web Admin.
   Envía el pedido al administrador (queda registrado y se avisa por email). Si el administrador no responde
   (caído, sin conexión, más de 12 segundos), ofrece un botón de WhatsApp con el mismo pedido ya armado.
   Sin configuración (window.GWA_FORM vacío) no hace nada: queda el pedido por WhatsApp de product.js.
   Protección: campo trampa invisible, tiempo mínimo de llenado (token firmado del servidor) y consentimiento explícito. */
(() => {
  const cfg = window.GWA_FORM;
  const form = document.querySelector(".pp-form");
  if (!cfg || !cfg.endpoint || !form) return;
  const status = form.querySelector(".pp-form-status");
  const submit = form.querySelector('button[type="submit"]');
  const ESPERA = 12000;
  const base = cfg.endpoint.replace(/\/$/, "");

  // Campo trampa: las personas no lo ven ni lo completan
  const hp = document.createElement("label");
  hp.className = "pp-form-hp";
  hp.setAttribute("aria-hidden", "true");
  hp.innerHTML = 'Sitio web <input name="sitio_web" tabindex="-1" autocomplete="off">';
  form.prepend(hp);

  // Consentimiento para el tratamiento de los datos
  const consent = document.createElement("label");
  consent.className = "pp-form-consent";
  consent.innerHTML = '<input type="checkbox" name="consentimiento" required> <span></span>';
  consent.querySelector("span").textContent = cfg.privacy || "Acepto que GENEOS use estos datos solo para responder mi consulta.";
  (submit.closest(".pp-form-actions") || submit).before(consent);

  const conEspera = (url, opciones = {}) => {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), ESPERA);
    return fetch(url, { ...opciones, signal: ctl.signal }).finally(() => clearTimeout(t));
  };

  let token = null;
  const getToken = () => {
    if (token) return;
    token = "pendiente";
    conEspera(base + "/token/?sitio=" + encodeURIComponent(cfg.site))
      .then((r) => r.json()).then((d) => { token = d.token; }).catch(() => { token = null; });
  };
  form.addEventListener("focusin", getToken, { once: true });

  // El mismo mensaje que arma product.js: producto, versión elegida y cada campo marcado con data-wa
  const mensajeWhatsApp = () => {
    const version = form.querySelector("input[type=radio]:checked");
    const lineas = ["Hola GENEOS, quiero solicitar una demo de " + (form.dataset.product || cfg.product || "") + (version ? " " + version.value : "") + "."];
    form.querySelectorAll("[data-wa]").forEach((el) => {
      const v = el.value.trim();
      if (v) lineas.push(el.dataset.wa + ": " + v + (el.dataset.suffix ? " " + el.dataset.suffix : ""));
    });
    return "https://wa.me/" + (cfg.whatsapp || "5492494521418") + "?text=" + encodeURIComponent(lineas.join("\n"));
  };

  const say = (msg, ok) => {
    if (!status) return;
    status.textContent = msg;
    status.className = "pp-form-status " + (ok ? "is-ok" : "is-err");
  };
  const ofrecerWhatsApp = (msg) => {
    say(msg + " ", false);
    if (!status) return;
    const a = document.createElement("a");
    a.className = "pp-btn pp-btn-primary pp-form-wa";
    a.href = mensajeWhatsApp();
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Enviar el pedido por WhatsApp";
    status.append(a);
  };

  // Fase de captura: corre antes que el envío por WhatsApp de product.js
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    e.stopImmediatePropagation();
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form).entries());
    data.sitio = cfg.site;
    data.producto = form.dataset.product || "";
    data.pagina = location.pathname;
    data.token = token && token !== "pendiente" ? token : "";
    submit.disabled = true;
    say("Enviando…", true);
    conEspera(base + "/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })
      .then((r) => r.json().catch(() => ({})).then((d) => ({ ok: r.ok, codigo: r.status, d })))
      .then(({ ok, codigo, d }) => {
        if (ok) {
          form.reset();
          say("¡Gracias! Recibimos tu pedido y te vamos a contactar pronto.", true);
        } else if (codigo >= 400 && codigo < 500 && d.error) {
          say(d.error, false);  // un dato a corregir: se arregla y se vuelve a enviar
        } else {
          ofrecerWhatsApp("No pudimos enviar el pedido en este momento.");
        }
      })
      .catch(() => ofrecerWhatsApp("No pudimos enviar el pedido en este momento."))
      .finally(() => { submit.disabled = false; });
  }, true);
})();
