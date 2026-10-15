/* «Blog y noticias»: filtros que se aplican solos, «Ver más ideas» y aviso mientras se actualizan las sugerencias.
   Sin JavaScript todo sigue funcionando: los filtros se envían con el botón y las ideas extra quedan ocultas. */
(() => {
  document.querySelectorAll(".gwa-bl-filtros [data-auto]").forEach((sel) => sel.addEventListener("change", () => sel.form.submit()));
  const mas = document.querySelector("[data-ver-mas]");
  mas?.addEventListener("click", () => {
    document.querySelectorAll("[data-ideas] [data-extra]").forEach((el) => (el.hidden = false));
    mas.remove();
  });
  document.querySelector("[data-actualizar]")?.closest("form")?.addEventListener("submit", (e) => {
    const b = e.currentTarget.querySelector("button");
    b.setAttribute("aria-disabled", "true");
    b.lastChild.textContent = "Actualizando…";
  });
})();
