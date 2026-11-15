/* Páginas de producto: pedido de demo por WhatsApp y preguntas frecuentes (una abierta a la vez). */
(() => {
  const WHATSAPP = "5492494521418";

  // Los enlaces "Solicitar demo" de una versión preseleccionan esa versión en el formulario
  document.querySelectorAll("[data-version]").forEach((a) => a.addEventListener("click", () => {
    const radio = document.getElementById("v-" + a.dataset.version);
    if (radio) radio.checked = true;
  }));

  document.querySelectorAll(".pp-form").forEach((form) => {
    const status = form.querySelector(".pp-form-status");
    const say = (text, kind) => { status.textContent = text; status.className = "pp-form-status" + (kind ? " is-" + kind : ""); };
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const name = form.elements.nombre, mail = form.elements.email;
      if (name && !name.value.trim()) { say("Completá tu nombre.", "err"); name.focus(); return; }
      if (mail && !/^\S+@\S+\.\S+$/.test(mail.value)) { say("Revisá el email: parece incompleto.", "err"); mail.focus(); return; }
      const version = form.querySelector("input[type=radio]:checked");
      const lines = ["Hola GENEOS, quiero solicitar una demo de " + form.dataset.product + (version ? " " + version.value : "") + "."];
      form.querySelectorAll("[data-wa]").forEach((el) => {
        const v = el.value.trim();
        if (v) lines.push(el.dataset.wa + ": " + v + (el.dataset.suffix ? " " + el.dataset.suffix : ""));
      });
      window.open("https://wa.me/" + WHATSAPP + "?text=" + encodeURIComponent(lines.join("\n")), "_blank", "noopener");
      say("Abrimos WhatsApp con tu pedido listo para enviar.", "ok");
    });
  });

  document.querySelectorAll(".pp-faq-list").forEach((list) => {
    const items = list.querySelectorAll("details");
    items.forEach((d) => d.addEventListener("toggle", () => {
      if (d.open) items.forEach((o) => { if (o !== d) o.open = false; });
    }));
  });
})();

/* Carrusel de trabajos: flechas que desplazan una tarjeta */
document.querySelectorAll('[data-rail]').forEach((rail) => {
  const track = rail.querySelector('[data-rail-track]');
  const step = () => (track.firstElementChild ? track.firstElementChild.getBoundingClientRect().width + 20 : track.clientWidth);
  rail.querySelector('[data-rail-prev]')?.addEventListener('click', () => track.scrollBy({ left: -step(), behavior: 'smooth' }));
  rail.querySelector('[data-rail-next]')?.addEventListener('click', () => track.scrollBy({ left: step(), behavior: 'smooth' }));
});
