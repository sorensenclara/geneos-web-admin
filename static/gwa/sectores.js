/* «Sectores»: filtros por producto (tarjetas o selector), línea, estado, presencia en la web y búsqueda. */
(() => {
  const raiz = document.querySelector("[data-sectores]");
  if (!raiz) return;
  const f = (k) => raiz.querySelector(`[data-filtro="${k}"]`);
  const filas = [...raiz.querySelectorAll("tr[data-sector]")];
  const tarjetas = [...raiz.querySelectorAll("[data-filtro-producto]")];
  const cuenta = raiz.querySelector("[data-cuenta]"), sinRes = raiz.querySelector("[data-sin-resultados]");
  const seccion = raiz.querySelector("[data-seccion-texto]"), anadir = raiz.querySelector("[data-anadir]");
  const norm = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  function filtrar() {
    const q = norm(f("q").value.trim()), prod = f("producto").value, linea = f("linea").value, estado = f("estado").value, web = f("web").value;
    let n = 0;
    filas.forEach((tr) => {
      const ok = (!q || norm(tr.dataset.nombre).includes(q)) && (!prod || tr.dataset.producto === prod) &&
        (!linea || tr.dataset.linea === linea) && (!estado || tr.dataset.estado === estado) && (!web || tr.dataset.web === web);
      tr.hidden = !ok;
      if (ok) n++;
    });
    cuenta.textContent = n === filas.length ? `${n} sector${n === 1 ? "" : "es"}` : `Mostrando ${n} de ${filas.length}`;
    sinRes.hidden = n > 0 || !filas.length;
    tarjetas.forEach((t) => t.setAttribute("aria-pressed", t.dataset.filtroProducto === prod ? "true" : "false"));
    const tpl = raiz.querySelector(`template[data-seccion="${prod}"]`);
    seccion.hidden = !tpl;
    if (tpl) seccion.textContent = tpl.innerHTML.trim();
    if (anadir) { const u = new URL(anadir.href, location.href); if (prod) u.searchParams.set("sitio", prod); else u.searchParams.delete("sitio"); anadir.href = u; }
    const url = new URL(location.href); if (prod) url.searchParams.set("sitio", prod); else url.searchParams.delete("sitio"); history.replaceState(null, "", url);
  }
  tarjetas.forEach((t) => t.addEventListener("click", () => {
    f("producto").value = t.getAttribute("aria-pressed") === "true" ? "" : t.dataset.filtroProducto;
    filtrar();
  }));
  ["producto", "linea", "estado", "web"].forEach((k) => f(k).addEventListener("change", filtrar));
  f("q").addEventListener("input", filtrar);
  raiz.querySelector("[data-limpiar]").addEventListener("click", () => {
    ["q", "producto", "linea", "estado", "web"].forEach((k) => (f(k).value = ""));
    filtrar();
  });
  filtrar();
})();
