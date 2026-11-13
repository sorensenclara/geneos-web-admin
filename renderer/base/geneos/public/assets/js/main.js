/* GENEOS · interacciones del sitio (sin dependencias) */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  /* Apariencia clara u oscura: la elección del visitante se guarda en el navegador */
  const raiz = document.documentElement;
  const temaBtn = $(".tema-toggle");
  const rotular = () => {
    if (!temaBtn) return;
    const claro = raiz.getAttribute("data-tema") === "claro";
    const texto = claro ? "Activar modo oscuro" : "Activar modo claro";
    temaBtn.setAttribute("aria-label", texto);
  };
  rotular();
  temaBtn?.addEventListener("click", () => {
    const nuevo = raiz.getAttribute("data-tema") === "claro" ? "oscuro" : "claro";
    raiz.setAttribute("data-tema", nuevo);
    try { localStorage.setItem("geneos-tema", nuevo); } catch (e) { /* sin almacenamiento: vale solo para esta página */ }
    rotular();
  });
  requestAnimationFrame(() => requestAnimationFrame(() => raiz.classList.add("tema-listo")));

  /* Menú móvil */
  const toggle = $(".nav-toggle");
  const nav = $("#menu");
  if (toggle && nav) {
    toggle.addEventListener("click", () => {
      nav.style.top = `${document.querySelector(".site-header").getBoundingClientRect().bottom}px`;
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open);
      document.body.classList.toggle("nav-open", open);
    });
  }
  $$(".sub-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const li = btn.closest("li");
      const open = li.classList.toggle("open");
      btn.setAttribute("aria-expanded", open);
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && nav?.classList.contains("open")) toggle.click();
  });

  /* Carruseles de fotos */
  $$(".carousel").forEach((c) => {
    const track = $(".carousel-track", c);
    const step = () => track.clientWidth;
    const go = (dir) => {
      const max = track.scrollWidth - track.clientWidth - 2;
      if (dir > 0 && track.scrollLeft >= max) track.scrollTo({ left: 0 });
      else if (dir < 0 && track.scrollLeft <= 0) track.scrollTo({ left: max });
      else track.scrollBy({ left: dir * step() });
    };
    $(".prev", c)?.addEventListener("click", () => go(-1));
    $(".next", c)?.addEventListener("click", () => go(1));
    const ms = +c.dataset.autoplay;
    if (ms && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      let t = setInterval(() => go(1), ms);
      c.addEventListener("mouseenter", () => clearInterval(t));
      c.addEventListener("mouseleave", () => (t = setInterval(() => go(1), ms)));
    }
  });

  /* Marquesinas: duplicamos los logos para un loop continuo */
  $$(".marquee-track").forEach((track) => {
    const items = [...track.children];
    items.forEach((li) => {
      const clone = li.cloneNode(true);
      clone.setAttribute("aria-hidden", "true");
      clone.querySelectorAll("a").forEach((a) => (a.tabIndex = -1));
      track.appendChild(clone);
    });
    track.style.setProperty("--marquee-duration", `${items.length * 3.5}s`);
  });

  /* Flip boxes en pantallas táctiles */
  $$(".flip").forEach((f) => f.addEventListener("click", () => f.classList.toggle("flipped")));

  /* Carrusel de socios (Quiénes somos): flechas sobre un scroll nativo con snap */
  $$(".qs-team").forEach((sec) => {
    const track = $(".qs-track", sec);
    const arrows = $$(".qs-arrow", sec);
    if (!track) return;
    const step = () => {
      const slide = track.firstElementChild;
      return slide ? slide.getBoundingClientRect().width + parseFloat(getComputedStyle(track).columnGap || 0) : track.clientWidth;
    };
    const update = () => {
      const max = track.scrollWidth - track.clientWidth - 2;
      arrows.forEach((b) => (b.disabled = +b.dataset.dir < 0 ? track.scrollLeft <= 2 : track.scrollLeft >= max));
    };
    arrows.forEach((b) => b.addEventListener("click", () => track.scrollBy({ left: +b.dataset.dir * step() })));
    track.addEventListener("scroll", () => requestAnimationFrame(update), { passive: true });
    addEventListener("resize", update);
    update();
  });

  /* Fichas del equipo: <dialog> nativo (Escape y foco atrapado por el navegador) */
  let opener = null;
  const openMember = (id) => {
    const dlg = document.getElementById(id);
    if (!dlg) return;
    $$("dialog.member[open]").forEach((d) => d.close());
    dlg.showModal();
    $(".member-close", dlg)?.focus();
  };
  $$("[data-member]").forEach((btn) => btn.addEventListener("click", () => { opener = btn; openMember(btn.dataset.member); }));
  $$("dialog.member").forEach((dlg) => {
    dlg.addEventListener("click", (e) => {
      if (e.target === dlg || e.target.closest(".member-close")) dlg.close();
      const go = e.target.closest("[data-goto]");
      if (go) {
        opener = document.querySelector(`[data-member="${go.dataset.goto}"]`) || opener;
        openMember(go.dataset.goto);
      }
    });
    dlg.addEventListener("close", () => {
      if (!$("dialog.member[open]") && opener) {
        opener.closest(".qs-slide")?.scrollIntoView({ block: "nearest", inline: "nearest" });
        opener.focus({ preventScroll: true });
      }
    });
  });

  /* Video del hero: una sola reproducción; sin animación si el usuario la reduce */
  const heroVideo = $(".hx-hero-video");
  if (heroVideo) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { heroVideo.removeAttribute("autoplay"); heroVideo.pause(); }
    heroVideo.loop = false;
  }

  /* Mensaje tras enviar el formulario */
  if (new URLSearchParams(location.search).has("enviado")) {
    $$(".form-status").forEach((p) => {
      p.hidden = false;
      p.textContent = "¡Gracias! Recibimos tu mensaje y te responderemos a la brevedad.";
    });
  }
})();
