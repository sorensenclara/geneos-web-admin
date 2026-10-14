/* Formulario de demo conectado a GENEOS Web Admin.
   Envía el pedido al administrador (queda registrado y se avisa por email). Si el servidor no responde,
   ofrece seguir por WhatsApp con el mensaje ya armado, como hasta ahora.
   Protección: campo trampa invisible, tiempo mínimo de llenado (token firmado del servidor) y consentimiento explícito. */
(() => {
  const cfg = window.GWA_FORM;
  const form = document.querySelector(".pp-form");
  if (!cfg || !cfg.endpoint || !form) return;
  const status = form.querySelector(".pp-form-status");
  const submit = form.querySelector('button[type="submit"]');

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

  let token = null;
  const getToken = () => {
    if (token) return;
    token = "pendiente";
    fetch(cfg.endpoint.replace(/\/$/, "") + "/token/?sitio=" + encodeURIComponent(cfg.site))
      .then((r) => r.json()).then((d) => { token = d.token; }).catch(() => { token = null; });
  };
  form.addEventListener("focusin", getToken, { once: true });

  const say = (msg, ok) => { if (status) { status.textContent = msg; status.className = "pp-form-status " + (ok ? "is-ok" : "is-err"); } };

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
    fetch(cfg.endpoint.replace(/\/$/, "") + "/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!ok) throw new Error(d.error || "No pudimos enviar el pedido.");
        form.reset();
        say("¡Gracias! Recibimos tu pedido y te vamos a contactar pronto.", true);
      })
      .catch((err) => {
        say(err.message + " Podés escribirnos por WhatsApp.", false);
      })
      .finally(() => { submit.disabled = false; });
  }, true);
})();
