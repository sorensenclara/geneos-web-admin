/* Sitio comercial: cierra el menú móvil al elegir una opción (los enlaces llevan a secciones de la misma página). */
(() => {
  const nav = document.getElementById("menu");
  const toggle = document.querySelector(".nav-toggle");
  if (!nav || !toggle) return;
  nav.addEventListener("click", (e) => {
    if (e.target.closest("a") && nav.classList.contains("open")) toggle.click();
  });
})();

/* Comparador de planes: "Ver comparación completa" y selector de plan en celulares */
(() => {
  document.querySelectorAll("[data-cmp]").forEach((cmp) => {
    const more = cmp.querySelector(".pp-cmp-more");
    if (more) {
      cmp.classList.add("is-collapsed");
      more.hidden = false;
      more.addEventListener("click", () => {
        const open = cmp.classList.toggle("is-collapsed") === false;
        more.setAttribute("aria-expanded", open);
      });
    }
    const tabs = cmp.querySelectorAll(".pp-cmp-tabs button");
    if (tabs.length) {
      cmp.classList.add("has-tabs");
      tabs.forEach((b) => b.addEventListener("click", () => {
        cmp.dataset.show = b.dataset.plan;
        tabs.forEach((t) => t.setAttribute("aria-pressed", t === b));
      }));
    }
  });
})();
