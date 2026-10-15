/* Buscador y filtro por categoría del blog: usan el índice de todos los artículos del listado (sin servidor). */
(() => {
  const datos = JSON.parse(document.getElementById("blog-indice")?.textContent || "null");
  if (!datos) return;
  const q = document.querySelector("[data-blog-search]"), cat = document.querySelector("[data-blog-cat]");
  const paginas = document.querySelector("[data-blog-paginas]"), res = document.querySelector("[data-blog-resultados]");
  const lista = document.querySelector("[data-blog-lista]"), cuenta = document.querySelector("[data-blog-cuenta]");
  const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function tarjeta(a) {
    const img = a.image ? `<img src="${datos.img || datos.base + "assets/"}${esc(a.image.src)}" alt="${esc(a.image.alt)}" width="${a.image.w}" height="${a.image.h}" loading="lazy">` : '<span class="bl-sin-img" aria-hidden="true"></span>';
    const meta = [datos.show_date ? esc(a.date_label) : "", esc(a.line_label)].filter(Boolean).join(" · ");
    return `<li><a class="pp-blog-card" href="${datos.base}${esc(a.path)}">${img}${a.categories[0] ? `<span class="bl-cat">${esc(a.categories[0])}</span>` : ""}<h2>${esc(a.title)}</h2><p>${esc(a.summary)}</p><span class="pp-blog-meta">${meta}</span></a></li>`;
  }
  function filtrar() {
    const t = norm(q?.value.trim()), c = cat?.value || "";
    const activo = Boolean(t || c);
    paginas.hidden = activo; res.hidden = !activo;
    if (!activo) return;
    const encontrados = datos.posts.filter((a) => (!c || a.categories.includes(c)) && (!t || norm(`${a.title} ${a.summary} ${a.categories.join(" ")}`).includes(t)));
    lista.innerHTML = encontrados.map(tarjeta).join("");
    cuenta.textContent = encontrados.length ? `${encontrados.length} artículo${encontrados.length > 1 ? "s" : ""}` : "No hay artículos que coincidan con la búsqueda.";
  }
  q?.addEventListener("input", filtrar);
  cat?.addEventListener("change", filtrar);
})();
