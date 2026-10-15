/* «Funcionalidades»: vistas Comparador/Lista, filtros, valores por plan, reordenar y cambios sin guardar.
   Sin JavaScript la pantalla sigue funcionando: todos los campos se envían y las vistas son enlaces. */
(() => {
  const form = document.getElementById("gwa-fx");
  if (!form) return;
  const ICONO = { incluido: "success", no_incluido: "circle-xmark", opcional: "circle-minus", texto: "type", a_confirmar: "help" };
  const tbody = form.querySelector("tbody");
  const filas = () => [...tbody.querySelectorAll("tr[data-fila]")];
  const valor = (el) => (el.type === "checkbox" ? String(el.checked) : el.value);
  const campos = [...form.querySelectorAll("input[name], select[name]")].filter((el) => !["csrfmiddlewaretoken", "sitio", "vista"].includes(el.name) && el.type !== "hidden" || el.matches("[data-orden]"));
  campos.forEach((el) => (el.dataset.original = valor(el)));
  const pkDe = (el) => el.closest("tr[data-fila]")?.dataset.fila;

  // ---------- Comparador / Lista ----------
  const campoVista = form.querySelector("[data-campo-vista]");
  document.querySelectorAll(".gwa-fx-vistas [data-vista]").forEach((tab) => {
    tab.addEventListener("click", (e) => {
      e.preventDefault();
      const v = tab.dataset.vista;
      form.dataset.vista = v;
      campoVista.value = v;
      document.querySelectorAll(".gwa-fx-vistas [data-vista]").forEach((t) => t.setAttribute("aria-selected", t === tab ? "true" : "false"));
      const url = new URL(location.href); url.searchParams.set("vista", v); history.replaceState(null, "", url);
      document.querySelectorAll("[data-producto]").forEach((a) => { const u = new URL(a.href); u.searchParams.set("vista", v); a.href = u; });
    });
  });

  // ---------- Valor por plan: ícono y texto personalizado acompañan lo elegido ----------
  form.querySelectorAll("[data-valor]").forEach((sel) => {
    const caja = sel.closest(".gwa-fx-valor");
    const texto = caja.querySelector("[data-texto]");
    sel.addEventListener("change", () => {
      caja.dataset.estado = sel.value;
      caja.querySelector(".gwa-fx-valor-icono use").setAttribute("href", "#icon-" + (ICONO[sel.value] || "help"));
      texto.hidden = sel.value !== "texto";
      texto.required = sel.value === "texto";
      if (sel.value === "texto") texto.focus();
    });
  });

  // ---------- Filtros y búsqueda ----------
  const f = (k) => form.querySelector(`[data-filtro="${k}"]`);
  const cuenta = form.querySelector("[data-cuenta]"), sinRes = form.querySelector("[data-sin-resultados]");
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  function filtrar() {
    const q = norm(f("q").value.trim()), grupo = f("grupo").value, estado = f("estado").value;
    let n = 0;
    filas().forEach((tr) => {
      const g = tr.querySelector("[data-grupo-campo]")?.value || tr.dataset.grupo;
      const conf = [...tr.querySelectorAll("[data-valor]")].some((s) => s.value === "a_confirmar");
      const resumen = tr.querySelector('input[name^="resumen_"][type="checkbox"]')?.checked;
      const visible = tr.querySelector('input[name^="visible_"][type="checkbox"]')?.checked;
      const ok = (!q || norm(tr.dataset.nombre).includes(q)) && (!grupo || g === grupo) &&
        (!estado || (estado === "a_confirmar" && conf) || (estado === "borrador" && tr.dataset.borrador === "1") ||
         (estado === "resumen" && resumen) || (estado === "oculta" && !visible));
      tr.hidden = !ok;
      if (ok) n++;
    });
    const total = filas().length;
    cuenta.textContent = n === total ? `${total} funcionalidad${total === 1 ? "" : "es"}` : `Mostrando ${n} de ${total}`;
    sinRes.hidden = n > 0;
  }
  ["q", "grupo", "estado"].forEach((k) => f(k).addEventListener(k === "q" ? "input" : "change", filtrar));

  // ---------- Orden: arrastrar o flechas, siempre dentro del mismo grupo ----------
  const grupoDe = (tr) => tr.querySelector("[data-grupo-campo]")?.value || tr.dataset.grupo;
  function renumerar() {
    filas().forEach((tr, i) => {
      tr.querySelector("[data-orden]").value = String(i + 1);
      tr.querySelector("[data-orden-texto]").textContent = String(i + 1);
    });
    actualizar();
  }
  function mover(tr, paso) {
    const hermanos = filas().filter((x) => grupoDe(x) === grupoDe(tr) && !x.hidden);
    const i = hermanos.indexOf(tr), j = i + paso;
    if (j < 0 || j >= hermanos.length) return false;
    if (paso < 0) hermanos[j].before(tr); else hermanos[j].after(tr);
    renumerar();
    return true;
  }
  let arrastrada = null;
  tbody.addEventListener("pointerdown", (e) => {
    const h = e.target.closest("[data-mover]");
    if (h) h.closest("tr").draggable = true;
  });
  tbody.addEventListener("dragstart", (e) => {
    arrastrada = e.target.closest("tr[data-fila]");
    if (!arrastrada) return;
    arrastrada.classList.add("is-arrastrando");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", arrastrada.dataset.fila);
  });
  tbody.addEventListener("dragover", (e) => {
    const destino = e.target.closest("tr[data-fila]");
    if (!arrastrada || !destino || destino === arrastrada || grupoDe(destino) !== grupoDe(arrastrada)) return;
    e.preventDefault();
    filas().forEach((tr) => tr.classList.toggle("is-destino", tr === destino));
  });
  tbody.addEventListener("drop", (e) => {
    const destino = e.target.closest("tr[data-fila]");
    if (!arrastrada || !destino || destino === arrastrada || grupoDe(destino) !== grupoDe(arrastrada)) return;
    e.preventDefault();
    const antes = filas().indexOf(arrastrada) > filas().indexOf(destino);
    if (antes) destino.before(arrastrada); else destino.after(arrastrada);
    renumerar();
  });
  tbody.addEventListener("dragend", () => {
    if (arrastrada) { arrastrada.classList.remove("is-arrastrando"); arrastrada.draggable = false; }
    filas().forEach((tr) => tr.classList.remove("is-destino"));
    arrastrada = null;
  });
  tbody.querySelectorAll("[data-paso]").forEach((b) => b.addEventListener("click", () => {
    if (mover(b.closest("tr"), Number(b.dataset.paso))) b.focus();
  }));
  tbody.querySelectorAll("[data-mover]").forEach((b) => b.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    if (mover(b.closest("tr"), e.key === "ArrowUp" ? -1 : 1)) b.focus();
  }));

  // Cambiar de grupo lleva la fila al final de su nuevo grupo (como se ordena en la web: primero las básicas)
  tbody.querySelectorAll("[data-grupo-campo]").forEach((sel) => sel.addEventListener("change", () => {
    const tr = sel.closest("tr");
    const delGrupo = filas().filter((x) => x !== tr && grupoDe(x) === sel.value);
    if (delGrupo.length) delGrupo[delGrupo.length - 1].after(tr);
    else if (sel.value === "basic") tbody.prepend(tr); else tbody.append(tr);
    tr.dataset.grupo = sel.value;
    renumerar();
    filtrar();
  }));

  // ---------- Cambios sin guardar ----------
  const barra = form.querySelector(".gwa-pr-barra"), resumen = form.querySelector("[data-resumen]");
  let enviando = false;
  const filasCambiadas = () => {
    const ids = new Set(campos.filter((el) => valor(el) !== el.dataset.original).map(pkDe));
    return filas().filter((tr) => ids.has(tr.dataset.fila));
  };
  function actualizar() {
    const cambiadas = filasCambiadas();
    filas().forEach((tr) => {
      const sucia = cambiadas.includes(tr);
      tr.classList.toggle("is-dirty", sucia);
      tr.querySelector("[data-cambio]").hidden = !sucia;
    });
    barra.classList.toggle("is-dirty", cambiadas.length > 0);
    resumen.textContent = cambiadas.length
      ? `Tenés cambios sin guardar en ${cambiadas.length} funcionalidad${cambiadas.length > 1 ? "es" : ""}.`
      : "No hay cambios sin guardar.";
    const pub = form.querySelector("[data-publicar]");
    if (pub) pub.toggleAttribute("aria-disabled", cambiadas.length > 0);
  }
  form.addEventListener("input", (e) => { if (!e.target.matches("[data-filtro]")) actualizar(); });
  form.addEventListener("change", (e) => { if (!e.target.matches("[data-filtro]")) actualizar(); });
  window.addEventListener("beforeunload", (e) => {
    if (!enviando && filasCambiadas().length) { e.preventDefault(); e.returnValue = ""; }
  });

  // ---------- Confirmación antes de aprobar ----------
  const dialogo = document.getElementById("gwa-fx-confirmar");
  form.addEventListener("submit", (e) => {
    const accion = e.submitter?.value;
    // texto personalizado obligatorio
    const vacio = [...form.querySelectorAll("[data-texto]:not([hidden])")].find((t) => !t.value.trim());
    if (vacio) { e.preventDefault(); vacio.setCustomValidity("Escribí el texto que se muestra en la web."); vacio.reportValidity(); vacio.addEventListener("input", () => vacio.setCustomValidity(""), { once: true }); return; }
    if (accion !== "aprobar" || form.dataset.confirmado === "1" || !dialogo?.showModal) { enviando = true; return; }
    e.preventDefault();
    const cambiadas = filasCambiadas();
    dialogo.querySelector("[data-dialogo-texto]").textContent = cambiadas.length
      ? `Se guardan y aprueban ${cambiadas.length} funcionalidad${cambiadas.length > 1 ? "es" : ""}:`
      : "No hay cambios nuevos. Se aprueban los borradores que ya estaban guardados.";
    dialogo.querySelector("[data-dialogo-lista]").replaceChildren(...cambiadas.map((tr) => {
      const li = document.createElement("li"); li.textContent = tr.dataset.nombre; return li;
    }));
    dialogo.querySelector("[data-dialogo-lista]").hidden = !cambiadas.length;
    dialogo.showModal();
  });
  dialogo?.addEventListener("close", () => {
    if (dialogo.returnValue !== "aprobar") return;
    form.dataset.confirmado = "1";
    enviando = true;
    const b = form.querySelector('[data-accion="aprobar"]');
    form.requestSubmit ? form.requestSubmit(b) : b.click();
  });
  document.querySelector("[data-publicar]")?.addEventListener("click", (e) => {
    if (filasCambiadas().length && !confirm("Tenés cambios sin guardar. Guardalos y aprobalos antes de publicar. ¿Salir igual?")) e.preventDefault();
    else enviando = true;
  });
  actualizar();
  filtrar();
})();
