/*
 * GENEOS UI · interacciones del esqueleto (sidebar, topbar, desplegables).
 * Portado de GELECTRIC (core/static/core/js/dashboard.js): initSidebarToggle, initSidebarTooltips,
 * initTopbarSearch e initBtnDropdowns, con submenús y cierre del cajón en el celular.
 * Sin dependencias externas.
 */
(function (window, document) {
  "use strict";

  var PIN_KEY = "gwa-sidebar-pinned";
  var mobileQuery = window.matchMedia("(max-width: 860px)");

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---------- menú lateral: cajón en el celular, "fijado" en escritorio ----------
  function initSidebarToggle() {
    var sidebar = document.getElementById("gu-sidebar");
    var scrim = document.getElementById("gu-scrim");
    var menuBtn = document.getElementById("gu-menu-btn");
    if (!sidebar || !scrim || !menuBtn) return;

    function setPinned(pinned) {
      sidebar.classList.toggle("pinned", pinned);
      menuBtn.setAttribute("aria-pressed", pinned ? "true" : "false");
      menuBtn.setAttribute("aria-label", pinned ? "Contraer el menú" : "Expandir el menú");
      try { localStorage.setItem(PIN_KEY, pinned ? "1" : "0"); } catch (e) {}
    }
    function setOpen(open) {
      sidebar.classList.toggle("open", open);
      scrim.classList.toggle("open", open);
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
      menuBtn.setAttribute("aria-label", open ? "Cerrar el menú" : "Abrir el menú");
      if (open) {
        var activo = sidebar.querySelector(".gu-nav-item.active") || sidebar.querySelector(".gu-nav-item");
        if (activo) activo.focus({ preventScroll: true });
      }
    }
    function syncMode() {
      if (mobileQuery.matches) {
        menuBtn.removeAttribute("aria-pressed");
        setOpen(false);
      } else {
        menuBtn.removeAttribute("aria-expanded");
        sidebar.classList.remove("open");
        scrim.classList.remove("open");
        setPinned(sidebar.classList.contains("pinned"));
      }
    }

    menuBtn.addEventListener("click", function () {
      if (mobileQuery.matches) setOpen(!sidebar.classList.contains("open"));
      else setPinned(!sidebar.classList.contains("pinned"));
    });
    scrim.addEventListener("click", function () { setOpen(false); menuBtn.focus(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && sidebar.classList.contains("open")) { setOpen(false); menuBtn.focus(); }
    });
    sidebar.querySelectorAll("a.gu-nav-item").forEach(function (el) {
      el.addEventListener("click", function () { if (mobileQuery.matches) setOpen(false); });
    });
    // Atajo de teclado de Wagtail para el menú lateral: «[»
    document.addEventListener("keydown", function (e) {
      var t = e.target;
      if (e.key !== "[" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      e.preventDefault();
      menuBtn.click();
    });
    mobileQuery.addEventListener("change", syncMode);
    syncMode();

    // Submenús: en el sidebar contraído, abrir un grupo expande el sidebar (así se ven sus opciones)
    sidebar.querySelectorAll("[data-gu-submenu]").forEach(function (btn) {
      var panel = document.getElementById(btn.getAttribute("aria-controls"));
      if (!panel) return;
      btn.addEventListener("click", function () {
        if (!mobileQuery.matches && !sidebar.classList.contains("pinned")) {
          setPinned(true);
          btn.setAttribute("aria-expanded", "true");
          panel.hidden = false;
          return;
        }
        var open = btn.getAttribute("aria-expanded") !== "true";
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        panel.hidden = !open;
      });
    });
  }

  // ---------- globito con el nombre de cada ícono (sidebar contraído) ----------
  function initSidebarTooltips() {
    var sidebar = document.getElementById("gu-sidebar");
    var tooltip = document.getElementById("gu-icon-tooltip");
    if (!sidebar || !tooltip) return;
    var deskQuery = window.matchMedia("(min-width: 861px)");

    function show(item) {
      if (!deskQuery.matches || sidebar.classList.contains("pinned")) return;
      var label = item.querySelector(".gu-nav-label");
      var text = label ? label.textContent.trim() : "";
      if (!text) return;
      var rect = item.getBoundingClientRect();
      tooltip.textContent = text;
      tooltip.style.top = (rect.top + rect.height / 2) + "px";
      tooltip.style.left = (rect.right + 12) + "px";
      tooltip.classList.add("visible");
    }
    function hide() { tooltip.classList.remove("visible"); }

    sidebar.querySelectorAll(".gu-nav-item").forEach(function (el) {
      el.addEventListener("mouseenter", function () { show(el); });
      el.addEventListener("mouseleave", hide);
      el.addEventListener("focus", function () { show(el); });
      el.addEventListener("blur", hide);
      el.addEventListener("click", hide);
    });
    sidebar.addEventListener("scroll", hide, { passive: true });
    deskQuery.addEventListener("change", hide);
  }

  // ---------- buscador del topbar ----------
  // Mientras se escribe (2+ caracteres) consulta el buscador del administrador y muestra
  // un desplegable; Enter sin elegir un resultado abre la página completa de resultados.
  // ---------- Buscador del menú lateral (como GELETRIC) ----------
  // Filtra en el navegador las secciones y opciones del menú: cuenta cualquier palabra de la etiqueta que empiece
  // con lo escrito, sin distinguir mayúsculas ni acentos. El índice se arma con los enlaces del propio menú.
  function initSidebarSearch() {
    var input = document.getElementById("gu-sidebar-search-input");
    var clear = document.getElementById("gu-sidebar-search-clear");
    var nav = document.getElementById("gu-sidebar-nav");
    var foot = document.getElementById("gu-sidebar-foot");
    var results = document.getElementById("gu-sidebar-results");
    if (!input || !nav || !results) return;
    function norm(s) { return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
    var index = [];
    nav.querySelectorAll("a.gu-nav-item").forEach(function (a) {
      var label = (a.querySelector(".gu-nav-label") || a).textContent.trim();
      var sub = a.closest(".gu-subnav");
      var parent = sub ? document.querySelector('[aria-controls="' + sub.id + '"]') : null;
      var icon = (parent || a).querySelector("svg.gu-icon");
      index.push({ label: label, parent: parent ? parent.querySelector(".gu-nav-label").textContent.trim() : "",
                   href: a.getAttribute("href"), target: a.getAttribute("target"), icon: icon ? icon.outerHTML : "" });
    });
    function matches(label, q) {
      var words = label.split(/[\s/,()\-·]+/);
      for (var i = 0; i < words.length; i++) { if (words[i] && norm(words[i]).indexOf(q) === 0) return true; }
      return false;
    }
    function render() {
      var query = input.value.trim();
      clear.hidden = !query;
      if (!query) { nav.hidden = false; if (foot) foot.hidden = false; results.hidden = true; results.innerHTML = ""; return; }
      var q = norm(query);
      var found = index.filter(function (e) { return matches(e.label, q) || (e.parent && matches(e.parent, q)); });
      nav.hidden = true; if (foot) foot.hidden = true; results.hidden = false;
      results.innerHTML = found.length ? found.map(function (e) {
        return '<a class="gu-nav-item gu-search-hit" role="listitem" href="' + escapeHtml(e.href) + '"' + (e.target ? ' target="_blank" rel="noopener noreferrer"' : "") + ">" +
          e.icon + '<span class="gu-nav-label"><b>' + escapeHtml(e.label) + "</b>" + (e.parent ? "<small>" + escapeHtml(e.parent) + "</small>" : "") + "</span></a>";
      }).join("") : '<p class="gu-sidebar-empty">Sin resultados para «' + escapeHtml(query) + "».</p>";
    }
    input.addEventListener("input", render);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = ""; render(); }
      if (e.key === "Enter") { var first = results.querySelector("a"); if (first) { e.preventDefault(); first.click(); } }
    });
    clear.addEventListener("click", function () { input.value = ""; render(); input.focus(); });
  }

  function initTopbarSearch() {
    var form = document.getElementById("gu-search-form");
    var input = document.getElementById("gu-search-input");
    var results = document.getElementById("gu-search-results");
    if (!form || !input || !results) return;
    var url = form.getAttribute("action");
    var debounceTimer = null, requestId = 0, current = -1;

    function links() { return results.querySelectorAll("a.gu-search-result"); }
    function close() {
      results.hidden = true; results.innerHTML = ""; current = -1;
      input.setAttribute("aria-expanded", "false");
    }
    function mark(i) {
      var ls = links();
      ls.forEach(function (a, j) { a.classList.toggle("is-current", j === i); a.setAttribute("aria-selected", j === i ? "true" : "false"); });
      current = i;
      if (ls[i]) ls[i].scrollIntoView({ block: "nearest" });
    }
    function render(query, data) {
      var html = "", n = 0;
      (data.grupos || []).forEach(function (g) {
        if (!g.items.length) return;
        html += '<p class="gu-search-group">' + escapeHtml(g.titulo) + "</p>";
        g.items.forEach(function (it) {
          n++;
          var visual = it.imagen
            ? '<img src="' + escapeHtml(it.imagen) + '" alt="">'
            : '<svg class="icon gu-icon" aria-hidden="true"><use href="#icon-' + escapeHtml(it.icono || "search") + '"></use></svg>';
          html += '<a class="gu-search-result" role="option" href="' + escapeHtml(it.url) + '">' + visual +
            '<span class="gu-search-result-text"><b>' + escapeHtml(it.titulo) + "</b>" +
            (it.detalle ? "<small>" + escapeHtml(it.detalle) + "</small>" : "") + "</span></a>";
        });
      });
      if (!n) html = '<p class="gu-search-empty">Sin resultados para “' + escapeHtml(query) + '”.</p>';
      html += '<a class="gu-search-all" href="' + url + "?q=" + encodeURIComponent(query) + '">Ver todos los resultados</a>';
      results.innerHTML = html;
      results.hidden = false;
      input.setAttribute("aria-expanded", "true");
      current = -1;
    }
    function search(query) {
      var thisRequest = ++requestId;
      fetch(url + "?formato=json&q=" + encodeURIComponent(query), { headers: { Accept: "application/json" }, credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (data) { if (thisRequest === requestId) render(query, data); })
        .catch(close);
    }

    input.addEventListener("input", function () {
      var query = input.value.trim();
      clearTimeout(debounceTimer);
      if (query.length < 2) { close(); return; }
      debounceTimer = setTimeout(function () { search(query); }, 200);
    });
    input.addEventListener("keydown", function (e) {
      var ls = links();
      if (e.key === "Escape") { close(); input.blur(); }
      else if (e.key === "ArrowDown" && ls.length) { e.preventDefault(); mark((current + 1) % ls.length); }
      else if (e.key === "ArrowUp" && ls.length) { e.preventDefault(); mark(current <= 0 ? ls.length - 1 : current - 1); }
      else if (e.key === "Enter" && current >= 0 && ls[current]) { e.preventDefault(); window.location.href = ls[current].href; }
    });
    document.addEventListener("click", function (e) {
      if (!results.hidden && !results.contains(e.target) && e.target !== input) close();
    });
    // ⌘K / Ctrl+K enfoca el buscador desde cualquier pantalla
    document.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.focus(); input.select(); }
    });
  }

  // ---------- botones con menú desplegable ----------
  function initBtnDropdowns() {
    var toggles = document.querySelectorAll("[data-gu-dropdown]");
    if (!toggles.length) return;
    function closeAll(except) {
      toggles.forEach(function (btn) {
        if (btn === except) return;
        var menu = document.getElementById(btn.getAttribute("data-gu-dropdown"));
        if (!menu) return;
        menu.hidden = true;
        btn.setAttribute("aria-expanded", "false");
      });
    }
    toggles.forEach(function (btn) {
      var menu = document.getElementById(btn.getAttribute("data-gu-dropdown"));
      if (!menu) return;
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var open = menu.hidden;
        closeAll(btn);
        menu.hidden = !open;
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) { var first = menu.querySelector("a, button"); if (first) first.focus(); }
      });
    });
    document.addEventListener("click", function () { closeAll(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeAll(); });
  }

  function init() {
    initSidebarToggle();
    initSidebarTooltips();
    initTopbarSearch();
    initSidebarSearch();
    initBtnDropdowns();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})(window, document);
