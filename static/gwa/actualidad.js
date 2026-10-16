/* Lectura de fuentes al ingresar al administrador: un pedido liviano (como máximo cada 10 minutos por pestaña).
   El servidor solo arranca una lectura si pasaron más de 24 horas desde la anterior y no hay otra en curso. */
(() => {
  const url = document.currentScript?.dataset.url;
  if (!url) return;
  try {
    const ultima = Number(sessionStorage.getItem("gwa-lectura") || 0);
    if (Date.now() - ultima < 600000) return;
    sessionStorage.setItem("gwa-lectura", String(Date.now()));
  } catch (e) { /* sin sessionStorage: se pide igual, el servidor evita duplicados */ }
  const csrf = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || window.wagtailConfig?.CSRF_TOKEN || "";
  fetch(url, { method: "POST", headers: { "X-CSRFToken": csrf }, credentials: "same-origin" })
    .then((r) => (r.ok ? r.json() : {}))
    .then((j) => { if (j.iniciada || j.leyendo) document.dispatchEvent(new CustomEvent("gwa:lectura")); })
    .catch(() => {});
})();
