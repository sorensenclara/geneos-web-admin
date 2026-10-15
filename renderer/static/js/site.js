/* Sitio comercial: cierra el menú móvil al elegir una opción (los enlaces llevan a secciones de la misma página). */
(() => {
  const nav = document.getElementById("menu");
  const toggle = document.querySelector(".nav-toggle");
  if (!nav || !toggle) return;
  nav.addEventListener("click", (e) => {
    if (e.target.closest("a") && nav.classList.contains("open")) toggle.click();
  });
})();

/* Desplegable del menú principal (GERP · Planes)
   «Planes» es un botón (aria-expanded + aria-controls) que abre y cierra la lista de opciones.
   Escritorio: abre al pasar el mouse o con clic; un clic sobre un desplegable abierto con clic lo cierra;
     se cierra al hacer clic afuera, al elegir una opción o al retirar el mouse del conjunto (con 250 ms de margen).
   Teclado: Enter/Espacio abren y cierran; ↓ abre y va a la primera opción; ↑/↓, Inicio y Fin recorren;
     Escape cierra y devuelve el foco a «Planes»; Tab recorre y cierra al salir del componente.
   Celular: tocar «Planes» abre y vuelve a tocarlo cierra; tocar afuera o cerrar el menú hamburguesa lo cierra. */
(() => {
  const items = [...document.querySelectorAll("[data-dd]")];
  if (!items.length) return;
  const DEMORA = 250;
  const escritorio = matchMedia("(min-width: 921px) and (hover: hover) and (pointer: fine)");
  const links = (li) => [...li.querySelectorAll(".nav-dd-menu a")];
  const estado = new Map(); // li -> {porMouse, timer}
  const set = (li, open, porMouse = false) => {
    const st = estado.get(li);
    clearTimeout(st.timer);
    st.porMouse = open && porMouse;
    li.classList.toggle("is-open", open);
    li.querySelector(".nav-dd-btn").setAttribute("aria-expanded", open);
  };
  const isOpen = (li) => li.classList.contains("is-open");
  const closeAll = (except) => items.forEach((li) => li !== except && isOpen(li) && set(li, false));

  items.forEach((li) => {
    estado.set(li, { porMouse: false, timer: 0 });
    const btn = li.querySelector(".nav-dd-btn");
    const menu = li.querySelector(".nav-dd-menu");

    // Mouse (solo escritorio): abrir al entrar, cerrar con demora al salir del conjunto botón + panel
    li.addEventListener("pointerenter", (e) => {
      if (e.pointerType !== "mouse" || !escritorio.matches) return;
      clearTimeout(estado.get(li).timer);
      if (!isOpen(li)) { closeAll(li); set(li, true, true); }
    });
    li.addEventListener("pointerleave", (e) => {
      if (e.pointerType !== "mouse" || !escritorio.matches || !isOpen(li)) return;
      const st = estado.get(li);
      clearTimeout(st.timer);
      st.timer = setTimeout(() => set(li, false), DEMORA);
    });

    // Clic, toque, Enter o Espacio sobre «Planes»
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const st = estado.get(li);
      // Si lo abrió el mouse al pasar, el primer clic lo deja abierto (no lo cierra «de golpe»)
      if (isOpen(li) && st.porMouse && e.detail > 0) { st.porMouse = false; return; }
      const open = !isOpen(li);
      closeAll(li);
      set(li, open);
    });
    btn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); closeAll(li); set(li, true); links(li)[0]?.focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); closeAll(li); set(li, true); links(li).at(-1)?.focus(); }
    });
    menu.addEventListener("keydown", (e) => {
      const l = links(li), i = l.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); l[(i + 1) % l.length].focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); l[(i - 1 + l.length) % l.length].focus(); }
      else if (e.key === "Home") { e.preventDefault(); l[0].focus(); }
      else if (e.key === "End") { e.preventDefault(); l[l.length - 1].focus(); }
    });
    // Elegir una opción cierra el desplegable (y la navegación sigue normalmente)
    menu.addEventListener("click", (e) => { if (e.target.closest("a")) set(li, false); });
    li.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && isOpen(li)) { e.stopPropagation(); set(li, false); btn.focus(); }
    });
    // Tab: cierra cuando el foco sale del componente
    li.addEventListener("focusout", (e) => { if (e.relatedTarget && !li.contains(e.relatedTarget)) set(li, false); });
  });

  // Clic o toque afuera
  document.addEventListener("click", (e) => { if (!e.target.closest("[data-dd]")) closeAll(); });
  // Cerrar el menú hamburguesa también cierra el desplegable
  const nav = document.getElementById("menu");
  if (nav) new MutationObserver(() => { if (!nav.classList.contains("open")) closeAll(); }).observe(nav, { attributes: true, attributeFilter: ["class"] });
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
