/* «Actualizar precios»: vigencia compartida, cambios sin guardar y confirmación de aprobación.
   Sin JavaScript la pantalla sigue funcionando: los campos por plan son los que se envían. */
(() => {
  const form = document.getElementById("gwa-precios");
  if (!form) return;
  const SIMBOLO = { ARS: "$", USD: "US$" };
  const valor = (el) => (el.type === "checkbox" ? String(el.checked) : el.value);
  const campos = [...form.querySelectorAll("input[name], select[name]")].filter((el) => el.name !== "csrfmiddlewaretoken");
  campos.forEach((el) => (el.dataset.original = valor(el)));

  // Vigencia: si todos los planes del sitio comparten leyenda y aviso, se editan una sola vez
  form.querySelectorAll("[data-vigencia]").forEach((bloque) => {
    const comun = bloque.querySelector("[data-comun]");
    const porPlan = bloque.querySelector("[data-porplan]");
    const grupo = (k) => [...bloque.querySelectorAll(`[data-vig="${k}"]`)];
    const iguales = ["leyenda_vigencia", "vigente_hasta"].every((k) => new Set(grupo(k).map((e) => e.value)).size === 1);
    if (!iguales) {
      porPlan.open = true; porPlan.hidden = false;
      porPlan.querySelector("summary").textContent = "Cada plan tiene su propia vigencia: ver y editar";
      return;
    }
    comun.hidden = false;
    if (grupo("leyenda_vigencia").length === 1) porPlan.hidden = true;
    comun.querySelectorAll("[data-comun-campo]").forEach((c) => {
      const k = c.dataset.comunCampo;
      c.value = grupo(k)[0].value;
      c.addEventListener("input", () => { grupo(k).forEach((e) => { e.value = c.value; }); actualizar(); });
    });
    // Si se edita un plan por separado, el campo común deja de representar a todos
    porPlan.addEventListener("input", () => {
      const sigue = ["leyenda_vigencia", "vigente_hasta"].every((k) => new Set(grupo(k).map((e) => e.value)).size === 1);
      comun.querySelectorAll("[data-comun-campo]").forEach((c) => {
        c.disabled = !sigue;
        c.placeholder = sigue ? "Sin leyenda" : "Varía por plan: editalo abajo";
        if (!sigue) c.value = ""; else c.value = grupo(c.dataset.comunCampo)[0].value;
      });
      const alc = comun.querySelector("[data-alcance]");
      if (!alc) return;
      alc.dataset.original ??= alc.textContent;
      alc.textContent = sigue ? alc.dataset.original : "(distinta en cada plan)";
    });
  });

  // Moneda e IVA: el símbolo y el «+ IVA» de la tarjeta acompañan lo elegido
  form.querySelectorAll("[data-plan]").forEach((card) => {
    const mon = card.querySelector("[data-moneda]"), iva = card.querySelector("[data-mas-iva]");
    mon?.addEventListener("change", () => card.querySelectorAll("[data-simbolo]").forEach((b) => (b.textContent = SIMBOLO[mon.value] || "$")));
    iva?.addEventListener("change", () => card.querySelectorAll("[data-iva]").forEach((i) => (i.hidden = !iva.checked)));
  });

  // Cambios sin guardar
  const barra = form.querySelector(".gwa-pr-barra"), resumen = form.querySelector("[data-resumen]");
  let enviando = false;
  const planesCambiados = () => {
    const ids = new Set(campos.filter((el) => valor(el) !== el.dataset.original).map((el) => el.name.split("_").pop()));
    return [...form.querySelectorAll("[data-plan]")].filter((c) => ids.has(c.dataset.plan));
  };
  function actualizar() {
    const cambiados = planesCambiados();
    form.querySelectorAll("[data-plan]").forEach((c) => {
      const sucio = cambiados.includes(c);
      c.classList.toggle("is-dirty", sucio);
      c.querySelector("[data-cambio]").hidden = !sucio;
    });
    barra.classList.toggle("is-dirty", cambiados.length > 0);
    resumen.textContent = cambiados.length
      ? `${cambiados.length} plan${cambiados.length > 1 ? "es" : ""} con cambios sin guardar.`
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
