/* Sitio comercial: cierra el menú móvil al elegir una opción (los enlaces llevan a secciones de la misma página). */
(() => {
  const nav = document.getElementById("menu");
  const toggle = document.querySelector(".nav-toggle");
  if (!nav || !toggle) return;
  nav.addEventListener("click", (e) => {
    if (e.target.closest("a") && nav.classList.contains("open")) toggle.click();
  });
})();

/* Submenús del menú principal (GERP · Planes)
   Patrón «disclosure»: el enlace navega y el botón de la flecha abre o cierra el submenú (aria-expanded).
   Teclado: Enter/Espacio en la flecha abre; ↓ abre y va a la primera opción; ↑/↓ recorren; Escape cierra y vuelve a la flecha.
   Se cierra al hacer clic afuera, al salir con Tab o al abrir otro. */
(() => {
  const items = [...document.querySelectorAll("[data-dd]")];
  if (!items.length) return;
  const links = (li) => [...li.querySelectorAll(".nav-dd-menu a")];
  const set = (li, open) => {
    li.classList.toggle("is-open", open);
    li.querySelector(".nav-dd-toggle").setAttribute("aria-expanded", open);
  };
  const closeAll = (except) => items.forEach((li) => li !== except && set(li, false));
  items.forEach((li) => {
    const btn = li.querySelector(".nav-dd-toggle");
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = !li.classList.contains("is-open");
      closeAll(li);
      set(li, open);
    });
    btn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); closeAll(li); set(li, true); links(li)[0]?.focus(); }
    });
    li.querySelector(".nav-dd-menu").addEventListener("keydown", (e) => {
      const l = links(li), i = l.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); l[(i + 1) % l.length].focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); l[(i - 1 + l.length) % l.length].focus(); }
      else if (e.key === "Home") { e.preventDefault(); l[0].focus(); }
      else if (e.key === "End") { e.preventDefault(); l[l.length - 1].focus(); }
    });
    li.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && li.classList.contains("is-open")) { e.stopPropagation(); set(li, false); btn.focus(); }
    });
    li.querySelector(".nav-dd-menu").addEventListener("click", (e) => { if (e.target.closest("a")) set(li, false); });
    li.addEventListener("focusout", (e) => { if (!li.contains(e.relatedTarget)) set(li, false); });
  });
  document.addEventListener("click", (e) => { if (!e.target.closest("[data-dd]")) closeAll(); });
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
