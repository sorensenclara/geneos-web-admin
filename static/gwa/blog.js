/* «Blog y noticias»: filtros que se aplican solos, «Ver más ideas», aviso mientras se actualiza y refresco de
   «Actualidad e ideas para publicar» cuando termina la lectura de fuentes en segundo plano (sin recargar la página).
   Sin JavaScript todo sigue funcionando: los filtros se envían con el botón y la sección se ve actualizada al recargar. */
(() => {
  const enlazar = (raiz) => {
    raiz.querySelectorAll(".gwa-bl-filtros [data-auto], .gwa-ac-filtros [data-auto]").forEach((sel) => sel.addEventListener("change", () => sel.form.submit()));
    raiz.querySelector("[data-actualizar]")?.closest("form")?.addEventListener("submit", (e) => {
      const b = e.currentTarget.querySelector("button");
      b.setAttribute("aria-disabled", "true");
      b.lastChild.textContent = "Actualizando…";
    });
  };
  enlazar(document);
  const mas = document.querySelector("[data-ver-mas]");
  mas?.addEventListener("click", () => {
    document.querySelectorAll("[data-ideas] [data-extra]").forEach((el) => (el.hidden = false));
    mas.remove();
  });

  // Lectura en segundo plano: consulta el estado y, al terminar, reemplaza solo la sección de actualidad.
  const seccion = () => document.querySelector(".gwa-acs");
  let esperando = false;
  const esperar = () => {
    const s = seccion();
    if (!s || esperando || !s.dataset.estado) return;
    esperando = true;
    s.querySelector("[data-leyendo]")?.removeAttribute("hidden");
    const consultar = () => fetch(s.dataset.estado, { credentials: "same-origin" }).then((r) => r.json()).then((j) => {
      if (j.leyendo) return setTimeout(consultar, 4000);
      return fetch(location.href, { credentials: "same-origin" }).then((r) => r.text()).then((html) => {
        const nueva = new DOMParser().parseFromString(html, "text/html").querySelector(".gwa-acs");
        const actual = seccion();
        if (nueva && actual) { actual.replaceWith(nueva); enlazar(nueva); }
        esperando = false;
      });
    }).catch(() => { esperando = false; });
    setTimeout(consultar, 2500);
  };
  if (seccion()?.dataset.leyendo === "1") esperar();
  document.addEventListener("gwa:lectura", esperar);
})();
