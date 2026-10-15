/* «Actualizar precios»: vigencia compartida, cambios sin guardar y confirmación de aprobación.
   Sin JavaScript la pantalla sigue funcionando: los campos por plan son los que se envían. */
(() => {
  const form = document.getElementById("gwa-precios");
  if (!form) return;
  const SIMBOLO = { ARS: "$", USD: "US$" };
  const valor = (el) => (el.type === "checkbox" ? String(el.checked) : el.value);
  const campos = [...form.querySelectorAll("input[name], select[name]")].filter((el) => el.name !== "csrfmiddlewaretoken");
  campos.forEach((el) => (el.dataset.original = valor(el)));

  // Vigencia: si todos los planes del producto comparten leyenda y aviso, se editan una sola vez en el encabezado.
  // Si cada plan tiene la suya, el campo común queda desactivado y se editan en «Vigencia, moneda e IVA por plan».
  form.querySelectorAll("[data-vigencia]").forEach((seccion) => {
    const comun = seccion.querySelector("[data-comun]");
    const porPlan = seccion.querySelector("[data-porplan]");
    const grupo = (k) => [...seccion.querySelectorAll(`[data-vig="${k}"]`)];
    const iguales = () => ["leyenda_vigencia", "vigente_hasta"].every((k) => new Set(grupo(k).map((e) => e.value)).size === 1);
    const alc = comun.querySelector("[data-alcance]");
    if (alc) alc.dataset.original = alc.textContent;
    function reflejar() {
      const sigue = iguales();
      comun.querySelectorAll("[data-comun-campo]").forEach((c) => {
        c.disabled = !sigue;
        c.placeholder = sigue ? "Sin leyenda" : "Varía por plan: editala abajo";
        c.value = sigue ? grupo(c.dataset.comunCampo)[0].value : "";
      });
      if (alc) alc.textContent = sigue ? alc.dataset.original : "(distinta en cada plan)";
      return sigue;
    }
    comun.querySelectorAll("[data-comun-campo]").forEach((c) => {
      c.addEventListener("input", () => { grupo(c.dataset.comunCampo).forEach((e) => { e.value = c.value; }); actualizar(); });
    });
    porPlan.addEventListener("input", reflejar);
    if (!reflejar()) porPlan.open = true;
  });

  // Plegar y desplegar cada producto
  form.querySelectorAll("[data-plegar]").forEach((b) => {
    const cuerpo = document.getElementById(b.getAttribute("aria-controls"));
    const nombre = b.getAttribute("aria-label").replace(/^Plegar /, "");
    b.addEventListener("click", () => {
      const abierto = b.getAttribute("aria-expanded") === "true";
      b.setAttribute("aria-expanded", abierto ? "false" : "true");
      b.setAttribute("aria-label", (abierto ? "Desplegar " : "Plegar ") + nombre);
      cuerpo.hidden = abierto;
    });
  });

  // Moneda e IVA: el símbolo y el «+ IVA» de cada plan acompañan lo elegido, y el encabezado lo resume
  const fila = (pk) => form.querySelector(`tr[data-plan="${pk}"]`);
  function resumirMoneda(seccion) {
    const monedas = [...seccion.querySelectorAll("[data-moneda]")].map((m) => m.value);
    const ivas = [...seccion.querySelectorAll("[data-mas-iva]")].map((i) => i.checked);
    const rm = seccion.querySelector("[data-resumen-moneda]"), ri = seccion.querySelector("[data-resumen-iva]");
    if (rm) rm.textContent = new Set(monedas).size === 1 ? `Moneda: ${monedas[0]}` : "Moneda: varía por plan";
    if (ri) ri.innerHTML = ivas.every(Boolean) ? '<span aria-hidden="true"> · </span>+ IVA' : ivas.some(Boolean) ? '<span aria-hidden="true"> · </span>IVA: varía por plan' : "";
  }
  form.querySelectorAll("[data-moneda]").forEach((mon) => mon.addEventListener("change", () => {
    fila(mon.dataset.planRef).querySelectorAll("[data-simbolo]").forEach((b) => (b.textContent = SIMBOLO[mon.value] || "$"));
    resumirMoneda(mon.closest("[data-sitio]"));
  }));
  form.querySelectorAll("[data-mas-iva]").forEach((iva) => iva.addEventListener("change", () => {
    fila(iva.dataset.planRef).querySelectorAll("[data-iva]").forEach((i) => (i.hidden = !iva.checked));
    resumirMoneda(iva.closest("[data-sitio]"));
  }));
  form.querySelectorAll("[data-sitio]").forEach(resumirMoneda);

  // Cambios sin guardar
  const barra = form.querySelector(".gwa-pr-barra"), resumen = form.querySelector("[data-resumen]");
  let enviando = false;
  const planesCambiados = () => {
    const ids = new Set(campos.filter((el) => valor(el) !== el.dataset.original).map((el) => el.name.split("_").pop()));
    return [...form.querySelectorAll("tr[data-plan]")].filter((c) => ids.has(c.dataset.plan));
  };
  function actualizar() {
    const cambiados = planesCambiados();
    form.querySelectorAll("tr[data-plan]").forEach((c) => {
      const sucio = cambiados.includes(c);
      c.classList.toggle("is-dirty", sucio);
      c.querySelector("[data-cambio]").hidden = !sucio;
    });
    barra.classList.toggle("is-dirty", cambiados.length > 0);
    resumen.textContent = cambiados.length
      ? `Tenés cambios sin guardar en ${cambiados.length} plan${cambiados.length > 1 ? "es" : ""}.`
      : "No hay cambios sin guardar.";
  }
  form.addEventListener("input", actualizar);
  form.addEventListener("change", actualizar);
  window.addEventListener("beforeunload", (e) => {
    if (!enviando && planesCambiados().length) { e.preventDefault(); e.returnValue = ""; }
  });

  // Confirmación antes de aprobar
  const dialogo = document.getElementById("gwa-confirmar");
  form.addEventListener("submit", (e) => {
    const accion = e.submitter?.value;
    if (!form.checkValidity()) { e.preventDefault(); form.reportValidity(); return; }
    if (accion !== "aprobar" || form.dataset.confirmado === "1" || !dialogo?.showModal) { enviando = true; return; }
    e.preventDefault();
    const cambiados = planesCambiados();
    dialogo.querySelector("[data-dialogo-texto]").textContent = cambiados.length
      ? `Se guardan y aprueban ${cambiados.length} plan${cambiados.length > 1 ? "es" : ""}:`
      : "No hay cambios nuevos. Se aprueban los borradores que ya estaban guardados.";
    const ul = dialogo.querySelector("[data-dialogo-lista]");
    ul.replaceChildren(...cambiados.map((c) => {
      const li = document.createElement("li");
      const monto = c.querySelector('input[name^="precio_"]').value, sim = c.querySelector("[data-simbolo]").textContent;
      li.textContent = `${c.dataset.nombre}: ${sim}${monto}`;
      return li;
    }));
    ul.hidden = !cambiados.length;
    dialogo.showModal();
  });
  dialogo?.addEventListener("close", () => {
    if (dialogo.returnValue !== "aprobar") return;
    form.dataset.confirmado = "1";
    enviando = true;
    const b = form.querySelector('[data-accion="aprobar"]');
    form.requestSubmit ? form.requestSubmit(b) : b.click();
  });
  actualizar();
})();
