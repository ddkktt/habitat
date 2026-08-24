/* Tablero de quejas de Puerto Vallarta — sin dependencias ni paso de compilación.
   En local lee /api/data y /api/articles; en GitHub Pages cae a data.json y
   articles.json exportados con server.py --export-static. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};

const CATEGORY_LABEL = {
  roads: "vialidades", water: "agua", drainage: "drenaje", flooding: "inundaciones",
  lighting: "alumbrado", power: "electricidad", trash: "basura",
  public_space: "espacio público", transit: "transporte",
  wildlife: "🐊 cocodrilos / fauna", other: "otro",
};
const DEFAULT_FOCUS_CATEGORIES = ["water", "drainage", "flooding", "trash"];
const STATUS_LABEL = {
  new_complaint: "queja nueva", ongoing: "en curso", failed_repair: "reparación fallida",
  resolved: "resuelto", unclear: "sin definir",
};
const CERTAINTY_LABEL = { exact: "exacta", approximate: "aproximada", none: "sin ubicación" };
/* Códigos que vienen en los datos; si aparece uno nuevo se muestra tal cual. */
const REASON_LABEL = {
  off_topic_other: "fuera de tema (otro)",
  off_topic_politics: "fuera de tema (política)",
  off_topic_crime: "fuera de tema (seguridad)",
  event_not_complaint: "evento, no una queja",
  official_statement_no_problem: "comunicado oficial sin problema reportado",
};
const SOURCE_STATUS_LABEL = { pending_human_approval: "pendiente de aprobación humana" };
/* Reading-order tiers. Nothing is discarded: a low tier is read last, not never.
   Old ranked files still carry read / maybe / screened_out for the same three. */
const BUCKET_LABEL = {
  priority_high: "prioridad alta", priority_medium: "prioridad media", priority_low: "prioridad baja",
  read: "prioridad alta", maybe: "prioridad media", screened_out: "prioridad baja",
};

let DATA = null;
let STATIC_ARTICLES = null;

async function fetchJson(path) {
  const resp = await fetch(path, { cache: "no-store" });
  if (!resp.ok) throw new Error(`${path} respondió ${resp.status}`);
  const payload = await resp.json();
  if (payload.error) throw new Error(payload.error);
  return payload;
}

async function fetchData() {
  try {
    return await fetchJson("/api/data");
  } catch (apiErr) {
    try {
      return await fetchJson("data.json");
    } catch (staticErr) {
      throw new Error(`${apiErr.message}; respaldo estático: ${staticErr.message}`);
    }
  }
}

async function staticArticleRows() {
  if (STATIC_ARTICLES) return STATIC_ARTICLES;
  const payload = await fetchJson("articles.json");
  STATIC_ARTICLES = Array.isArray(payload) ? payload : (payload.items || []);
  return STATIC_ARTICLES;
}

function countPairs(values) {
  const counts = new Map();
  values.forEach((value) => {
    if (value) counts.set(value, (counts.get(value) || 0) + 1);
  });
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), "es"));
}

async function staticArticlePage(query) {
  const params = new URLSearchParams(query);
  const q = (params.get("q") || "").trim().toLowerCase();
  const bucket = params.get("bucket") || "";
  const category = params.get("category") || "";
  const outlet = params.get("outlet") || "";
  const from = params.get("from") || "";
  const to = params.get("to") || "";
  const recorded = params.get("recorded") === "1";

  const out = (await staticArticleRows()).filter((r) => {
    if (q) {
      const hay = [r.title, r.outlet, r.url, ...(r.categories || []), ...(r.signals || [])]
        .join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (bucket && r.bucket !== bucket) return false;
    if (category && !(r.categories || []).includes(category)) return false;
    if (outlet && r.outlet !== outlet) return false;
    if (from && (!r.date || r.date < from)) return false;
    if (to && (!r.date || r.date > to)) return false;
    if (recorded && !r.recorded) return false;
    return true;
  });

  const sort = params.get("sort") || "score";
  if (sort === "date") {
    out.sort((a, b) => (b.date || "").localeCompare(a.date || "") || (b.score || 0) - (a.score || 0));
  } else if (sort === "date_asc") {
    out.sort((a, b) => (a.date || "").localeCompare(b.date || "") || (a.score || 0) - (b.score || 0));
  } else {
    out.sort((a, b) => (b.score || 0) - (a.score || 0) || (b.date || "").localeCompare(a.date || ""));
  }

  let per = parseInt(params.get("per") || "50", 10);
  let page = parseInt(params.get("page") || "1", 10);
  if (!Number.isFinite(per)) per = 50;
  if (!Number.isFinite(page)) page = 1;
  per = Math.max(10, Math.min(200, per));
  page = Math.max(1, page);
  const start = (page - 1) * per;

  return {
    total: out.length, page, per,
    pages: Math.max(1, Math.ceil(out.length / per)),
    facets: {
      buckets: countPairs(out.map((r) => r.bucket)),
      outlets: countPairs(out.map((r) => r.outlet)),
      categories: countPairs(out.flatMap((r) => r.categories || [])),
    },
    items: out.slice(start, start + per),
  };
}

async function fetchArticles(query) {
  try {
    return await fetchJson("/api/articles?" + query);
  } catch (apiErr) {
    try {
      return await staticArticlePage(query);
    } catch (staticErr) {
      throw new Error(`${apiErr.message}; respaldo estático: ${staticErr.message}`);
    }
  }
}

function focusInfo() {
  const f = (DATA && DATA.focus) || {};
  return {
    title: f.title || "Agua y residuos",
    label: f.label || "agua, drenaje, inundaciones y residuos",
    categories: f.categories || DEFAULT_FOCUS_CATEGORIES,
    all_incidents: f.all_incidents || (DATA ? DATA.incidents.length : 0),
    all_records: f.all_records || (DATA ? DATA.records.length : 0),
  };
}

function visibleCategories(categories) {
  const keep = new Set(focusInfo().categories);
  return (categories || []).filter((c) => keep.has(c));
}

function visibleCategoryPairs(pairs) {
  const keep = new Set(focusInfo().categories);
  return (pairs || []).filter(([c]) => keep.has(c));
}

function orderedCategories(values) {
  const order = focusInfo().categories;
  const rank = new Map(order.map((c, i) => [c, i]));
  return [...values].filter((c) => rank.has(c))
    .sort((a, b) => rank.get(a) - rank.get(b));
}

/* ---------------------------------------------------------------- tema */
const savedTheme = (() => { try { return localStorage.getItem("pv-theme"); } catch { return null; } })();
if (savedTheme) document.documentElement.dataset.theme = savedTheme;
$("#theme-btn").addEventListener("click", () => {
  const now = document.documentElement.dataset.theme;
  const dark = now ? now === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const next = dark ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("pv-theme", next); } catch { /* ventana privada */ }
});

/* ---------------------------------------------------------------- pestañas */
/* Cada nav .tabs gobierna solo los paneles de su propia sección — la de
   arriba manda sobre las dos vistas (.view), las de adentro sobre sus .panel —
   así el expediente y la capa social llevan pestañas independientes. */
function showTab(tab) {
  const nav = tab.closest(".tabs");
  if (!nav) return;
  const sel = nav.dataset.target || ".panel";
  nav.querySelectorAll(".tab").forEach((t) => t.classList.toggle("is-on", t === tab));
  nav.parentElement.querySelectorAll(sel)
    .forEach((p) => { p.hidden = p.id !== tab.dataset.panel; });
  /* Leaflet mide su contenedor al pintarse: si el mapa estuvo oculto en la
     otra vista, la medida quedó en 0×0 y hay que rehacerla al volver. */
  if (MAP && !$("#v-map").hidden) setTimeout(() => MAP.invalidateSize(), 0);
  /* Cambiar de vista es cambiar de página: se vuelve arriba, y si el clic
     venía de un ancla, el scroll al destino manda después. */
  if (nav.classList.contains("primary")) window.scrollTo({ top: 0 });
}

document.querySelectorAll(".tabs .tab").forEach((tab) => {
  tab.addEventListener("click", () => showTab(tab));
});

/* Un ancla puede apuntar a una sección que vive en la otra vista; antes de
   saltar, se abre la pestaña que la contiene. */
function revealTarget(node) {
  const view = node && node.closest(".view");
  if (!view || !view.hidden) return;
  const tab = document.querySelector(`.tabs.primary .tab[data-panel="${view.id}"]`);
  if (tab) showTab(tab);
}

document.addEventListener("click", (ev) => {
  const link = ev.target.closest('a[href^="#"]');
  if (!link) return;
  const target = document.getElementById(link.getAttribute("href").slice(1));
  if (!target) return;
  ev.preventDefault();
  revealTarget(target);
  target.scrollIntoView({ behavior: "smooth" });
});

/* ---------------------------------------------------------------- carga */
async function load() {
  $("#status").textContent = "Cargando…";
  $("#status").classList.remove("error");
  try {
    DATA = await fetchData();
    render();
    $("#status").hidden = true;
    $("#app").hidden = false;
    /* Leaflet mide su contenedor al crearse; si eso ocurrió con #app oculto,
       la medida fue 0×0 y el mapa queda desplazado hasta recalcular. */
    if (MAP) setTimeout(() => MAP.invalidateSize(), 0);
  } catch (err) {
    $("#status").hidden = false;
    $("#status").className = "status error";
    $("#status").textContent = "No se pudo cargar el conjunto de datos: " + err.message +
      ". ¿Ya se ejecutó algún ciclo? (python3 feeds.py, luego store.py y cycle.py)";
  }
}
$("#reload-btn").addEventListener("click", load);

/* ---------------------------------------------------------------- pintado */
function render() {
  const t = DATA.totals;

  const focus = focusInfo();
  const hidden = Math.max(focus.all_incidents - t.incidents, 0);
  const cycles = DATA.cycles;
  if (cycles.length) {
    const last = cycles[cycles.length - 1];
    $("#source-line").textContent =
      `Foco temporal: ${focus.label} · ${t.incidents} incidentes visibles` +
      (hidden ? ` de ${focus.all_incidents}` : "") +
      ` · ciclo ${last.cycle}: ${last.scanned} artículos revisados`;
  } else {
    $("#source-line").textContent =
      `Foco temporal: ${focus.label} · ${t.incidents} incidentes visibles` +
      (hidden ? ` de ${focus.all_incidents}` : "");
  }

  initMapSection();
  buildFilters();
  renderFocusHighlight();
  renderIncidents();
  initNews();
  renderColonias();
  renderCredits();
  renderSocial();
  renderCycles();
  renderLearning();
  renderReading();
  initArticles();
  $("#report-md").textContent = DATA.report ? DATA.report.markdown : "Todavía no hay informe.";
}

function renderFocusHighlight() {
  const focus = focusInfo();
  const hidden = Math.max(focus.all_incidents - DATA.incidents.length, 0);
  $("#focus-title").textContent = focus.title;
  $("#focus-copy").textContent =
    `${DATA.incidents.length} incidentes y ${DATA.records.length} artículos quedan a la vista` +
    (hidden ? `; ${hidden} incidentes de otras categorías están ocultos por ahora.` : ".");

  const counts = {};
  DATA.incidents.forEach((inc) => {
    visibleCategories(inc.categories).forEach((c) => { counts[c] = (counts[c] || 0) + 1; });
  });

  const box = $("#focus-breakdown");
  box.textContent = "";
  orderedCategories(focus.categories).forEach((c) => {
    const row = el("button", "focus-topic");
    row.type = "button";
    row.title = "Filtrar por " + (CATEGORY_LABEL[c] || c);
    row.append(el("span", null, CATEGORY_LABEL[c] || c),
      el("span", "n", String(counts[c] || 0)));
    row.addEventListener("click", () => {
      stopMapPlay();
      mapState.cat = c;
      $("#m-category").value = c;
      $("#f-category").value = c;
      updateMap();
      renderIncidents();
    });
    box.appendChild(row);
  });
}

/* ---------------------------------------------------------------- mapa */
/* El mapa es un visor: dibuja incidentes ya almacenados sobre coordenadas
   aproximadas de state/colonia_coords.json. Nunca escribe ni geocodifica. */
const MONTH_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
let MAP = null, MAP_LAYER = null, HOT_LAYER = null, ZONE_LAYER = null,
    mapMonths = [], mapWired = false, mapPlayTimer = null;
const mapState = { cat: "", status: "", month: null };

const monthKey = (d) => (d || "").slice(0, 7);
const monthLabel = (k) => MONTH_ES[+k.slice(5, 7) - 1] + " " + k.slice(0, 4);
const cssColor = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#2a78d6";

function coordFor(name) {
  const cc = DATA.colonia_coords || {};
  const table = cc.colonias || {};
  return table[name] || table[(cc.aliases || {})[name]] || null;
}

/* El recorte del mapa: los mismos filtros de la barra, sin exigir colonia.
   Las tablas de la izquierda y los círculos leen de aquí, así nunca se separan. */
function mapSlice(skip) {
  return DATA.incidents.filter((inc) => {
    if (skip !== "cat" && mapState.cat && !visibleCategories(inc.categories).includes(mapState.cat)) return false;
    if (skip !== "status" && mapState.status && inc.status !== mapState.status) return false;
    if (skip !== "month" && mapState.month !== null &&
        monthKey(inc.first_article_date) !== mapMonths[mapState.month]) return false;
    return true;
  });
}

function mapAgg() {
  const agg = new Map();
  mapSlice().forEach((inc) => {
    if (!inc.colonia) return;
    let a = agg.get(inc.colonia);
    if (!a) agg.set(inc.colonia, a = { n: 0, cats: {} });
    a.n += 1;
    visibleCategories(inc.categories).forEach((c) => { a.cats[c] = (a.cats[c] || 0) + 1; });
  });
  return agg;
}

/* Lleva la lista de incidentes del riel a un texto: una colonia desde el
   mapa o el ranking, o una firma desde el panel de colaboradores. */
function focusSearch(query) {
  revealTarget($("#p-incidents"));
  showRailTab("p-incidents");
  $("#f-reset").click();
  $("#f-search").value = query;
  renderIncidents();
  $("#p-incidents").scrollIntoView({ behavior: "smooth" });
}

function stopMapPlay() {
  if (mapPlayTimer) { clearInterval(mapPlayTimer); mapPlayTimer = null; $("#m-play").textContent = "▶"; }
}

function setMapMonth(m) {
  mapState.month = m;
  document.querySelectorAll("#m-months .mchip").forEach((b) => {
    b.classList.toggle("on", b.dataset.m === (m === null ? "" : String(m)));
  });
  updateMap();
}

function initMapSection() {
  mapMonths = [...new Set(DATA.incidents.map((i) => monthKey(i.first_article_date)))].sort();

  const cats = new Set(), statuses = new Set();
  DATA.incidents.forEach((inc) => {
    visibleCategories(inc.categories).forEach((c) => cats.add(c));
    statuses.add(inc.status);
  });
  const keepCat = $("#m-category").value, keepSt = $("#m-status").value;
  fill($("#m-category"), orderedCategories(cats).map((c) => ({ value: c, label: CATEGORY_LABEL[c] || c })), "Todo el foco");
  fill($("#m-status"), [...statuses].sort().map((s) => ({ value: s, label: STATUS_LABEL[s] || s })), "Cualquier estado");
  $("#m-category").value = keepCat; $("#m-status").value = keepSt;

  const chips = $("#m-months");
  chips.textContent = "";
  const mkChip = (label, m) => {
    const b = el("button", "mchip" + ((mapState.month === m || (m === null && mapState.month === null)) ? " on" : ""), label);
    b.type = "button";
    b.dataset.m = m === null ? "" : String(m);
    b.addEventListener("click", () => { stopMapPlay(); setMapMonth(m); });
    chips.appendChild(b);
  };
  mkChip("Todo", null);
  mapMonths.forEach((k, i) => mkChip(monthLabel(k), i));

  if (!mapWired) {
    mapWired = true;
    $("#m-category").addEventListener("input", () => { mapState.cat = $("#m-category").value; updateMap(); });
    $("#m-status").addEventListener("input", () => { mapState.status = $("#m-status").value; updateMap(); });
    $("#m-hot").addEventListener("input", updateMap);
    $("#m-crocs-toggle").addEventListener("input", updateCrocZones);
    $("#m-play").addEventListener("click", () => {
      if (mapPlayTimer) { stopMapPlay(); return; }
      let m = mapState.month === null ? -1 : mapState.month;
      $("#m-play").textContent = "⏸";
      const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const step = () => {
        m += 1;
        if (m >= mapMonths.length) { stopMapPlay(); setMapMonth(null); return; }
        setMapMonth(m);
      };
      step();
      mapPlayTimer = setInterval(step, reduce ? 2000 : 1000);
    });
    /* el cambio de tema repinta los círculos con los colores del tema nuevo */
    $("#theme-btn").addEventListener("click", () => { if (MAP) updateMap(); });
  }

  const box = $("#map");
  if (!window.L) {
    box.textContent = "";
    const msg = el("p", "note", "El mapa necesita conexión a internet para cargar Leaflet y las teselas de " +
      "OpenStreetMap. El resto del tablero funciona sin conexión; recarga cuando haya red.");
    msg.style.padding = "16px";
    box.appendChild(msg);
  } else if (!MAP) {
    MAP = L.map("map", { scrollWheelZoom: true }).setView([20.645, -105.218], 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(MAP);
    /* orden de dibujo: sombras de colonias calientes y zonas de contexto
       debajo, círculos de incidentes encima */
    HOT_LAYER = L.layerGroup().addTo(MAP);
    ZONE_LAYER = L.layerGroup().addTo(MAP);
    MAP_LAYER = L.layerGroup().addTo(MAP);
  }
  updateMap();
}

function updateMap() {
  const agg = mapAgg();
  const total = [...agg.values()].reduce((s, a) => s + a.n, 0);
  const unmapped = [];

  if (MAP_LAYER) {
    MAP_LAYER.clearLayers();
    const color = cssColor("--series-1");
    const ring = cssColor("--surface-1");
    [...agg.entries()].sort((a, b) => b[1].n - a[1].n).forEach(([name, a]) => {
      const pos = coordFor(name);
      if (!pos) { unmapped.push([name, a.n]); return; }
      const marker = L.circleMarker([pos.lat, pos.lon], {
        radius: 7 + Math.sqrt(a.n) * 5,
        color: ring, weight: 2, fillColor: color, fillOpacity: 0.75,
      });
      const pop = el("div");
      pop.appendChild(el("strong", null, name));
      pop.appendChild(el("div", null, `${a.n} incidente${a.n === 1 ? "" : "s"}`));
      Object.entries(a.cats).sort((x, y) => y[1] - x[1]).slice(0, 3).forEach(([c, n]) => {
        pop.appendChild(el("div", "byline", `${CATEGORY_LABEL[c] || c}: ${n}`));
      });
      const go = el("button", "pop-link", "Ver los incidentes →");
      go.type = "button";
      go.addEventListener("click", () => focusSearch(name));
      pop.appendChild(go);
      marker.bindPopup(pop);
      marker.bindTooltip(`${name}: ${a.n}`);
      MAP_LAYER.addLayer(marker);
    });
  } else {
    [...agg.entries()].forEach(([name, a]) => { if (!coordFor(name)) unmapped.push([name, a.n]); });
  }

  /* Zonas calientes: sombrea las 10 colonias con más incidentes del filtro
     actual (las mismas del ranking lateral). Con la categoría en fauna, esto
     se vuelve "dónde se concentran los avistamientos" conforme haya datos. */
  if (HOT_LAYER) {
    HOT_LAYER.clearLayers();
    if ($("#m-hot").checked) {
      const hot = cssColor("--series-2");
      [...agg.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 10).forEach(([name, a]) => {
        const pos = coordFor(name);
        if (!pos) return;
        HOT_LAYER.addLayer(L.circle([pos.lat, pos.lon], {
          radius: 650, stroke: false, fillColor: hot, fillOpacity: 0.18,
        }).bindTooltip(`${name}: ${a.n} incidente${a.n === 1 ? "" : "s"} con el filtro actual`));
      });
    }
  }
  updateCrocZones();

  const periodo = (mapState.month === null ? "todo el periodo" : monthLabel(mapMonths[mapState.month])) +
    (mapState.cat ? " · " + (CATEGORY_LABEL[mapState.cat] || mapState.cat) : " · todo el foco") +
    (mapState.status ? " · " + (STATUS_LABEL[mapState.status] || mapState.status) : "");
  $("#m-label").textContent = `${total} incidentes con colonia · ${periodo}`;

  renderMapStats(total);

  const top = $("#m-top");
  top.textContent = "";
  const rows = [...agg.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 10);
  rows.forEach(([name, a]) => {
    const b = el("button", "m-top-row");
    b.type = "button";
    b.append(el("span", null, name), el("span", "n", String(a.n)));
    b.addEventListener("click", () => focusSearch(name));
    top.appendChild(b);
  });
  if (!rows.length) top.appendChild(el("p", "empty", "Ninguna colonia coincide con el filtro."));

  unmapped.sort((a, b) => b[1] - a[1]);
  $("#m-unmapped").textContent = unmapped.length
    ? `Sin coordenadas en colonia_coords.json (${unmapped.reduce((s, u) => s + u[1], 0)} incidentes): ` +
      unmapped.map(([n2, c]) => `${n2} (${c})`).join(", ") + "."
    : "Todas las colonias del filtro tienen coordenadas.";

  const cov = DATA.coverage || {};
  const master = cov.colonia_master_list, heard = cov.colonias_heard_from || [];
  $("#m-coverage").textContent = Array.isArray(master) && master.length
    ? `Hueco de cobertura: de las ${master.length} colonias de la lista maestra, ` +
      `${master.filter((c) => !heard.includes(c)).length} nunca han aparecido en un reporte ubicado.`
    : "";
}

/* Capa de contexto: zonas con presencia conocida de cocodrilos, de
   state/context_zones.json (mantenida a mano, como colonia_coords.json).
   Es conocimiento de fondo para leer el mapa: nunca entra a ningún conteo. */
function updateCrocZones() {
  if (!DATA) return;
  const zones = (DATA.context_zones || {}).zones || [];
  const mapOn = zones.length > 0 && $("#m-crocs-toggle").checked;

  if (ZONE_LAYER) {
    ZONE_LAYER.clearLayers();
    if (mapOn) {
      const warn = cssColor("--warn");
      zones.forEach((z) => {
        const circle = L.circle([z.lat, z.lon], {
          radius: z.radius_m || 700,
          color: warn, weight: 1.5, dashArray: "5 4",
          fillColor: warn, fillOpacity: 0.16,
        });
        const pop = el("div");
        pop.appendChild(el("strong", null, "🐊 " + z.name));
        pop.appendChild(el("div", "byline", z.water_body));
        pop.appendChild(el("div", null, z.note));
        if (z.seasonal) pop.appendChild(el("div", "byline", "mayor presencia en temporada de lluvias"));
        pop.appendChild(el("div", "byline", "capa de contexto — no es un incidente reportado"));
        circle.bindPopup(pop);
        circle.bindTooltip("🐊 " + z.name);
        ZONE_LAYER.addLayer(circle);
      });
    }
  }

  const mapNote = $("#m-croc");
  mapNote.hidden = !mapOn;
  if (mapOn) {
    mapNote.textContent = "🐊 Zona punteada = presencia conocida de cocodrilos (esteros y desembocaduras de ríos; " +
      "contexto local mantenido a mano en state/context_zones.json). Es fondo para leer el mapa, no incidentes reportados.";
  }

  const rail = $("#rail-crocs");
  const ctx = $("#croc-context");
  rail.hidden = zones.length === 0;
  ctx.textContent = "";
  if (zones.length) {
    ctx.appendChild(el("p", "kind", "🐊 Contexto: zonas con presencia conocida de cocodrilos"));
    ctx.appendChild(el("p", null, mapOn
      ? "Las zonas punteadas del mapa son contexto local; no son incidentes y no afectan los conteos."
      : "La capa está apagada en el mapa, pero estas zonas quedan como referencia local."));
    zones.forEach((z) => {
      const row = el("p");
      row.appendChild(el("b", null, z.name));
      row.append(document.createTextNode(" — " + z.note));
      ctx.appendChild(row);
    });
  }
}

/* ---------------------------------------------- tablas de estadísticas */
/* Cuentan sobre el recorte del mapa, no sobre el corpus completo: lo que se ve
   dibujado y lo que dicen los números es siempre la misma rebanada. Cada fila
   es un filtro; al hacer clic cambia el mapa igual que la barra de arriba. */
const pct = (n, total) => (total ? Math.round(1000 * n / total) / 10 : 0);

function statRow(tbody, cells, opts) {
  const tr = el("tr", opts && opts.on ? "st-row on" : (opts && opts.onClick ? "st-row" : null));
  cells.forEach((value, i) => {
    const td = el("td", i ? "num" : null);
    if (i === 0) td.appendChild(el("span", "st-name", String(value)));
    else td.textContent = String(value);
    tr.appendChild(td);
  });
  if (opts && opts.title) tr.title = opts.title;
  if (opts && opts.onClick) tr.addEventListener("click", opts.onClick);
  tbody.appendChild(tr);
  return tr;
}

function statBody(sel, colspan) {
  const tbody = $(sel).tBodies[0];
  tbody.textContent = "";
  tbody.dataset.colspan = colspan;
  return tbody;
}

function statEmpty(tbody) {
  if (tbody.rows.length) return;
  const tr = el("tr");
  const td = el("td", "st-empty", "sin datos con este filtro");
  td.colSpan = +tbody.dataset.colspan || 3;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

/* Los selects del mapa mandan; las filas solo los mueven y redibujan. */
function setMapFilter(key, value) {
  stopMapPlay();
  mapState[key] = mapState[key] === value ? "" : value;
  $(key === "cat" ? "#m-category" : "#m-status").value = mapState[key];
  updateMap();
}

function renderMapStats(withColonia) {
  const slice = mapSlice();
  const total = slice.length;
  $("#st-slice").textContent = total === DATA.incidents.length
    ? `${total} incidentes — todo el foco.`
    : `${total} de ${DATA.incidents.length} incidentes en el recorte del mapa.`;

  /* Categorías. Un incidente puede traer varias, así que la suma de la columna
     puede pasar del total; el porcentaje es sobre incidentes, no sobre etiquetas. */
  const catSlice = mapSlice("cat");
  const catCounts = new Map();
  catSlice.forEach((inc) => {
    visibleCategories(inc.categories).forEach((c) => catCounts.set(c, (catCounts.get(c) || 0) + 1));
  });
  let tb = statBody("#st-cats", 3);
  orderedCategories(catCounts.keys()).forEach((c) => {
    const n = catCounts.get(c);
    statRow(tb, [CATEGORY_LABEL[c] || c, n, pct(n, catSlice.length) + "%"], {
      on: mapState.cat === c,
      title: "Filtrar el mapa por " + (CATEGORY_LABEL[c] || c),
      onClick: () => setMapFilter("cat", c),
    });
  });
  statEmpty(tb);

  const stSlice = mapSlice("status");
  const stCounts = new Map();
  stSlice.forEach((inc) => stCounts.set(inc.status, (stCounts.get(inc.status) || 0) + 1));
  tb = statBody("#st-status", 3);
  [...stCounts.entries()].sort((a, b) => b[1] - a[1]).forEach(([st, n]) => {
    statRow(tb, [STATUS_LABEL[st] || st, n, pct(n, stSlice.length) + "%"], {
      on: mapState.status === st,
      title: "Filtrar el mapa por " + (STATUS_LABEL[st] || st),
      onClick: () => setMapFilter("status", st),
    });
  });
  statEmpty(tb);

  /* Meses: se ignora el mes elegido para que la tabla siga siendo el
     calendario completo del recorte y se pueda saltar de un mes a otro. */
  const mSlice = mapSlice("month");
  const mCounts = new Map();
  mSlice.forEach((inc) => {
    const k = monthKey(inc.first_article_date);
    if (!k) return;
    let m = mCounts.get(k);
    if (!m) mCounts.set(k, m = { n: 0, colonias: new Set() });
    m.n += 1;
    if (inc.colonia) m.colonias.add(inc.colonia);
  });
  tb = statBody("#st-months", 3);
  mapMonths.forEach((k, i) => {
    const m = mCounts.get(k);
    if (!m) return;
    statRow(tb, [monthLabel(k), m.n, m.colonias.size], {
      on: mapState.month === i,
      title: "Ver solo " + monthLabel(k),
      onClick: () => { stopMapPlay(); setMapMonth(mapState.month === i ? null : i); },
    });
  });
  statEmpty(tb);

  /* Medios: artículos e incidentes distintos que tocó cada redacción. */
  const outlets = new Map();
  slice.forEach((inc) => {
    const seen = new Set();
    inc.records.forEach((r) => {
      const name = r.source_outlet || "sin medio";
      let o = outlets.get(name);
      if (!o) outlets.set(name, o = { arts: 0, inc: 0 });
      o.arts += 1;
      if (!seen.has(name)) { seen.add(name); o.inc += 1; }
    });
  });
  tb = statBody("#st-outlets", 3);
  [...outlets.entries()].sort((a, b) => b[1].arts - a[1].arts).slice(0, 8).forEach(([name, o]) => {
    statRow(tb, [name, o.arts, o.inc], {
      title: "Buscar “" + name + "” en los incidentes",
      onClick: () => focusSearch(name),
    });
  });
  statEmpty(tb);

  const certCounts = { exact: 0, approximate: 0, none: 0 };
  slice.forEach((inc) => { certCounts[bestCertainty(inc)] += 1; });
  tb = statBody("#st-cert", 3);
  ["exact", "approximate", "none"].forEach((c) => {
    statRow(tb, [CERTAINTY_LABEL[c], certCounts[c], pct(certCounts[c], total) + "%"]);
  });

  const sinColonia = total - withColonia;
  $("#st-foot").textContent =
    `${withColonia} de estos ${total} incidentes traen colonia y se dibujan en el mapa` +
    (sinColonia ? `; ${sinColonia} no la traen y solo cuentan en estas tablas.` : ".") +
    " Un incidente con varias categorías cuenta en cada una.";
}

/* ------------------------------------------------------ noticias (riel) */
/* El riel tiene dos vistas de la misma realidad: el flujo de artículos tal como
   salieron publicados, y los incidentes ya agrupados. La lista de noticias vive
   en el servidor (/api/articles): el archivo rankeado pesa megabytes, así que se
   filtra y pagina allá y aquí solo se pide la ventana que se va a pintar. */
const newsState = { sort: "date", page: 1, pages: 1, total: 0 };
let newsWired = false, newsTimer = null;

function showRailTab(panelId) {
  const nav = document.querySelector(".rail-tabs");
  if (!nav) return;
  nav.querySelectorAll(".tab").forEach((t) => t.classList.toggle("is-on", t.dataset.panel === panelId));
  nav.parentElement.querySelectorAll(".panel").forEach((p) => { p.hidden = p.id !== panelId; });
}

function newsQuery() {
  const p = new URLSearchParams();
  const put = (k, v) => { if (v) p.set(k, v); };
  put("q", $("#n-search").value.trim());
  put("category", $("#n-category").value);
  put("outlet", $("#n-outlet").value);
  p.set("sort", $("#n-sort").value || "date");
  if ($("#n-recorded").checked) p.set("recorded", "1");
  p.set("page", String(newsState.page));
  p.set("per", "25");
  return p.toString();
}

/* Fechas cortas para el riel: "24 ago" dentro del año, con año si es otro. */
function shortDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  const label = `${+d} ${MONTH_ES[+m - 1] || ""}`;
  const now = (DATA.corpus && DATA.corpus.last) || "";
  return now.slice(0, 4) === y ? label : `${label} ${y}`;
}

function newsItem(r) {
  const li = el("li", "news " + (r.recorded ? "rec" : ""));
  const head = el("p", "news-meta");
  head.append(el("time", null, shortDate(r.date)), el("span", "dot", "·"),
    el("span", null, r.outlet || "sin medio"));
  if (r.author) head.append(el("span", "dot", "·"), el("span", null, r.author));
  li.appendChild(head);

  const t = el("a", "news-title", r.title || "(sin título)");
  t.href = r.url; t.target = "_blank"; t.rel = "noopener noreferrer";
  li.appendChild(t);

  if (r.snippet) li.appendChild(el("p", "news-snip", "…" + r.snippet.replace(/^…|…$/g, "") + "…"));

  const tags = el("div", "tags");
  visibleCategories(r.categories).forEach((c) => {
    const tag = el("button", "tag cat", CATEGORY_LABEL[c] || c);
    tag.type = "button";
    tag.title = "Ver solo " + (CATEGORY_LABEL[c] || c);
    tag.addEventListener("click", () => { $("#n-category").value = c; loadNews(); });
    tags.appendChild(tag);
  });
  if (r.recorded) tags.appendChild(el("span", "tag rec", "con registro"));
  if (tags.childElementCount) li.appendChild(tags);
  return li;
}

async function loadNews(append) {
  const list = $("#news-list");
  const more = $("#n-more");
  if (!append) { list.textContent = ""; newsState.page = 1; }
  more.hidden = true;
  const loading = el("p", "empty", "Cargando…");
  list.appendChild(loading);

  let data;
  try {
    data = await fetchArticles(newsQuery());
  } catch (err) {
    loading.textContent = "No se pudieron cargar las noticias: " + err.message;
    return;
  }
  loading.remove();

  newsState.total = data.total; newsState.pages = data.pages;

  /* Las facetas vienen del recorte actual; se repuebla conservando la elección. */
  const cat = $("#n-category").value, out = $("#n-outlet").value;
  const cats = orderedCategories(data.facets.categories.map(([c]) => c)).map((c) => {
    const hit = data.facets.categories.find(([name]) => name === c);
    return { value: c, label: `${CATEGORY_LABEL[c] || c} (${hit ? hit[1] : 0})` };
  });
  fill($("#n-category"), cats, "Todo el foco");
  fill($("#n-outlet"), data.facets.outlets.map(([o, n]) => ({ value: o, label: `${o} (${n})` })), "Todos los medios");
  $("#n-category").value = cat; $("#n-outlet").value = out;

  data.items.forEach((r) => list.appendChild(newsItem(r)));
  $("#news-empty").hidden = data.total > 0;

  const shown = Math.min(data.page * data.per, data.total);
  $("#n-count").textContent = data.total
    ? `${shown.toLocaleString()} de ${data.total.toLocaleString()} artículos`
    : "";
  more.hidden = data.page >= data.pages;
  more.textContent = `Cargar más (${(data.total - shown).toLocaleString()} restantes)`;
}

function initNews() {
  $("#n-intro").textContent = DATA.corpus
    ? `Artículos sobre ${focusInfo().label}, del ${DATA.corpus.last} hacia atrás. ` +
      `El titular abre la nota en su medio; «con registro» marca las que ya dieron ficha al mapa.`
    : "El flujo de artículos del corpus, del más reciente al más viejo.";
  if (newsWired) { loadNews(); return; }
  newsWired = true;
  ["#n-category", "#n-outlet", "#n-sort", "#n-recorded"]
    .forEach((sel) => $(sel).addEventListener("input", () => loadNews()));
  $("#n-search").addEventListener("input", () => {
    clearTimeout(newsTimer);
    newsTimer = setTimeout(loadNews, 220);
  });
  $("#n-reset").addEventListener("click", () => {
    ["#n-search", "#n-category", "#n-outlet"].forEach((s2) => { $(s2).value = ""; });
    $("#n-sort").value = "date";
    $("#n-recorded").checked = false;
    loadNews();
  });
  $("#n-more").addEventListener("click", () => { newsState.page += 1; loadNews(true); });
  loadNews();
}

/* ---------------------------------------------------------------- filtros */
function fill(select, values, allLabel) {
  select.textContent = "";
  select.appendChild(new Option(allLabel, ""));
  values.forEach((v) => select.appendChild(new Option(v.label, v.value)));
}

function buildFilters() {
  const cats = new Set(), statuses = new Set(), outlets = new Set();
  DATA.incidents.forEach((inc) => {
    visibleCategories(inc.categories).forEach((c) => cats.add(c));
    statuses.add(inc.status);
    inc.records.forEach((r) => outlets.add(r.source_outlet));
  });
  fill($("#f-category"), orderedCategories(cats).map((c) => ({ value: c, label: CATEGORY_LABEL[c] || c })), "Todo el foco");
  fill($("#f-status"), [...statuses].sort().map((s) => ({ value: s, label: STATUS_LABEL[s] || s })), "Cualquier estado");
  fill($("#f-certainty"), ["exact", "approximate", "none"].map((c) => ({ value: c, label: CERTAINTY_LABEL[c] })), "Cualquier ubicación");
  fill($("#f-outlet"), [...outlets].sort().map((o) => ({ value: o, label: o })), "Todos los medios");
}

["#f-search", "#f-category", "#f-status", "#f-certainty", "#f-outlet", "#f-unsure"]
  .forEach((sel) => $(sel).addEventListener("input", renderIncidents));
$("#f-reset").addEventListener("click", () => {
  ["#f-search", "#f-category", "#f-status", "#f-certainty", "#f-outlet"].forEach((s) => { $(s).value = ""; });
  $("#f-unsure").checked = false;
  renderIncidents();
});

function bestCertainty(inc) {
  const order = ["exact", "approximate", "none"];
  return inc.records.map((r) => r.location_certainty)
    .sort((a, b) => order.indexOf(a) - order.indexOf(b))[0] || "none";
}

function matches(inc) {
  const q = $("#f-search").value.trim().toLowerCase();
  if (q) {
    const hay = [inc.summary, inc.street, inc.colonia, inc.landmark,
      ...inc.categories, inc.status,
      ...inc.records.map((r) => [r.location_evidence, r.author, r.source_outlet,
        r.affected_people_clue, r.duration_clue].join(" "))].join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  const cat = $("#f-category").value;
  if (cat && !visibleCategories(inc.categories).includes(cat)) return false;
  if ($("#f-status").value && inc.status !== $("#f-status").value) return false;
  if ($("#f-certainty").value && bestCertainty(inc) !== $("#f-certainty").value) return false;
  const outlet = $("#f-outlet").value;
  if (outlet && !inc.records.some((r) => r.source_outlet === outlet)) return false;
  if ($("#f-unsure").checked && !inc.records.some((r) => r.qualifies === "unsure")) return false;
  return true;
}

function renderIncidents() {
  const list = $("#incident-list");
  list.textContent = "";
  const shown = DATA.incidents.filter(matches);
  shown.forEach((inc) => list.appendChild(card(inc)));
  $("#incident-empty").hidden = shown.length > 0;
  $("#slice-label").textContent =
    shown.length === DATA.incidents.length
      ? `${shown.length} incidente${shown.length === 1 ? "" : "s"}`
      : `${shown.length} de ${DATA.incidents.length} incidentes`;
  updateCrocZones();
}

function card(inc) {
  const certainty = bestCertainty(inc);
  const li = el("li", "card " + certainty);
  const head = el("div", "card-head");
  head.appendChild(el("p", "card-sum", inc.summary));
  const dates = inc.first_article_date === inc.last_article_date
    ? inc.first_article_date
    : `${inc.first_article_date} → ${inc.last_article_date}`;
  head.appendChild(el("span", "byline", dates));
  li.appendChild(head);

  const place = el("p", "card-place");
  const parts = [];
  if (inc.colonia) parts.push(["colonia", inc.colonia]);
  if (inc.street) parts.push(["en", inc.street]);
  if (inc.landmark) parts.push(["cerca de", inc.landmark]);
  if (parts.length) {
    parts.forEach(([label, value], i) => {
      if (i) place.append(document.createTextNode(" · "));
      place.append(document.createTextNode(label + " "), el("b", null, value));
    });
  } else {
    place.append(document.createTextNode("el artículo no indica una ubicación"));
  }
  li.appendChild(place);

  const tags = el("div", "tags");
  visibleCategories(inc.categories).forEach((c) => tags.appendChild(el("span", "tag cat", CATEGORY_LABEL[c] || c)));
  tags.appendChild(el("span", "tag", STATUS_LABEL[inc.status] || inc.status));
  tags.appendChild(el("span", "tag", "ubicación: " + CERTAINTY_LABEL[certainty]));
  if (inc.coverage_count > 1) tags.appendChild(el("span", "tag cov", `cubierto ${inc.coverage_count}×`));
  if (inc.records.some((r) => r.qualifies === "unsure")) {
    tags.appendChild(el("span", "tag unsure", "pendiente de revisión humana"));
  }
  li.appendChild(tags);

  inc.records.forEach((rec) => {
    if (rec.location_evidence) li.appendChild(el("p", "quote", "“" + rec.location_evidence + "”"));
    const clues = el("p", "clues");
    if (rec.duration_clue) clues.appendChild(el("span", null, "⏱ " + rec.duration_clue));
    if (rec.affected_people_clue) clues.appendChild(el("span", null, "👥 " + rec.affected_people_clue));
    if (clues.childElementCount) li.appendChild(clues);
  });

  const srcs = el("div", "srcs");
  inc.records.forEach((rec) => {
    const row = el("div");
    const link = el("a", null, rec.source_outlet + " — " + rec.article_date);
    link.href = rec.article_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    row.appendChild(link);
    if (rec.author) row.appendChild(el("span", "byline", " · por " + rec.author));
    srcs.appendChild(row);
  });
  li.appendChild(srcs);
  return li;
}

/* ---------------------------------------------------------------- colonias */
function renderColonias() {
  const cr = DATA.colonia_rank || { ranked: [], unlocated: 0 };
  const total = cr.ranked.reduce((sum, r) => sum + r.incidents, 0);
  $("#col-intro").textContent = cr.ranked.length
    ? `${total} incidentes ubicados en ${cr.ranked.length} colonias, ordenadas por número de incidentes. ` +
      `«Artículos» cuenta la cobertura de prensa: un incidente al que los medios vuelven varias veces pesa más.`
    : "Todavía no hay incidentes con colonia.";

  const body = $("#colonia-table").tBodies[0];
  body.textContent = "";
  cr.ranked.forEach((r, i) => {
    const tr = el("tr");
    tr.appendChild(el("td", "num rank" + (i < 3 ? " top" : ""), String(i + 1)));
    const td = el("td");
    const link = el("button", "rowlink", r.colonia);
    link.type = "button";
    link.title = "Ver los incidentes de " + r.colonia;
    link.addEventListener("click", () => focusSearch(r.colonia));
    td.appendChild(link);
    tr.appendChild(td);
    [r.incidents, r.articles, r.open, r.resolved].forEach((n) =>
      tr.appendChild(el("td", "num", String(n))));
    tr.appendChild(el("td", null, visibleCategoryPairs(r.categories).slice(0, 2)
      .map(([c, n]) => `${CATEGORY_LABEL[c] || c} (${n})`).join(", ")));
    tr.appendChild(el("td", null, r.last));
    body.appendChild(tr);
  });

  $("#col-noloc").textContent = cr.unlocated
    ? `${cr.unlocated} incidente${cr.unlocated === 1 ? " no trae" : "s no traen"} colonia en el artículo, ` +
      `así que quedan fuera del ranking: en el tablero aparecen como «sin ubicación», no se adivinan.`
    : "";
}

/* ---------------------------------------------------------------- colaboradores */
/* El agradecimiento del tablero: cada dato viene de la prensa local, y esta
   pestaña le da el crédito a quien firmó ese trabajo. Las firmas salen del
   propio medio (registro, índice del corpus o página cacheada); nunca se
   inventa una autoría. */
function renderCredits() {
  const cred = DATA.collaborators || { authors: [], credited: 0, uncredited: 0 };
  const people = cred.authors.filter((a) => a.kind === "person");
  const desks = cred.authors.filter((a) => a.kind === "desk");

  $("#cred-intro").textContent =
    "Este mapa existe porque alguien salió a reportear. Gracias a las y los periodistas de la bahía " +
    "cuyo trabajo alimenta cada ficha — este es su crédito, con enlace a sus artículos en cada incidente.";

  const list = $("#cred-people");
  list.textContent = "";
  people.forEach((a, i) => {
    const li = el("li", "cred" + (i < 3 ? " top" : ""));
    const rank = el("span", "cred-rank", String(i + 1));
    rank.setAttribute("aria-hidden", "true");
    const body = el("div", "cred-body");

    const name = el("button", "cred-name", a.name);
    name.type = "button";
    name.title = "Ver los incidentes que documentó";
    name.addEventListener("click", () => focusSearch(a.name));
    body.appendChild(name);
    body.appendChild(el("p", "byline", a.outlets.map(([o]) => o).join(" · ")));

    const bits = [
      `${a.records} ${a.records === 1 ? "artículo registrado" : "artículos registrados"}`,
      `${a.incidents} incidente${a.incidents === 1 ? "" : "s"}`,
      `${a.located} con ubicación`,
    ];
    if (a.colonias.length) bits.push("colonias: " + a.colonias.join(", "));
    body.appendChild(el("p", "cred-stats", bits.join(" · ")));

    if (a.categories.length) {
      const tags = el("div", "tags");
      visibleCategoryPairs(a.categories).slice(0, 3).forEach(([c, n]) =>
        tags.appendChild(el("span", "tag cat", `${CATEGORY_LABEL[c] || c} ${n}`)));
      body.appendChild(tags);
    }
    li.append(rank, body);
    list.appendChild(li);
  });
  if (!people.length) list.appendChild(el("p", "empty", "Ningún registro trae todavía una firma personal."));

  barRows($("#cred-desks"), desks.map((a) => [a.name, a.records]), "--series-2");

  const totalRecs = cred.credited + cred.uncredited;
  $("#cred-uncredited").textContent =
    `${cred.credited} de ${totalRecs} artículos registrados traen firma; los ${cred.uncredited} restantes ` +
    `se publicaron sin autor identificable, así que su crédito queda con el medio que los publicó.`;
}

/* ---------------------------------------------------------------- capa social */
/* La capa social tiene sección propia, con tres pestañas: top colaboradores
   (reconocimientos calculados de las fechas de los registros), colonias (las
   voces que cubren cada una) y el ranking con el puntaje completo. Solo
   firmas de prensa — los registros de redes sociales viajan sin autor por
   diseño y nunca entran aquí. */
const SOC_SCORE = (a) =>
  a.records + a.incidents + 3 * a.primicias + 2 * a.seguimientos;
function renderSocial() {
  const cred = DATA.collaborators || { authors: [], colonia_voices: {} };

  $("#soc-intro").textContent =
    "Quién abre las historias y quién no las suelta: una primicia es la primera firma sobre un " +
    "incidente que después recibió más cobertura; un seguimiento es volver a una historia ya " +
    "abierta — la cobertura repetida es presión pública.";

  const honored = cred.authors
    .filter((a) => a.primicias || a.seguimientos)
    .sort((x, y) => (y.primicias - x.primicias) || (y.seguimientos - x.seguimientos));
  const list = $("#soc-honors");
  list.textContent = "";
  honored.forEach((a, i) => {
    const li = el("li", "cred" + (i < 3 ? " top" : ""));
    const rank = el("span", "cred-rank", String(i + 1));
    rank.setAttribute("aria-hidden", "true");
    const body = el("div", "cred-body");
    const name = el("button", "cred-name", a.name);
    name.type = "button";
    name.title = "Ver los incidentes que documentó";
    name.addEventListener("click", () => focusSearch(a.name));
    body.appendChild(name);
    body.appendChild(el("p", "byline", a.outlets.map(([o]) => o).join(" · ")));
    const tags = el("div", "tags");
    if (a.primicias) {
      const t = el("span", "tag honor", `primicia ×${a.primicias}`);
      t.title = "Primera firma sobre un incidente que después recibió más cobertura";
      tags.appendChild(t);
    }
    if (a.seguimientos) {
      const t = el("span", "tag honor", `seguimiento ×${a.seguimientos}`);
      t.title = "Volvió a una historia ya abierta";
      tags.appendChild(t);
    }
    body.appendChild(tags);
    body.appendChild(el("p", "cred-stats", [
      `${a.records} ${a.records === 1 ? "artículo" : "artículos"}`,
      `${a.incidents} incidente${a.incidents === 1 ? "" : "s"}`,
      `puntaje ${SOC_SCORE(a)}`,
    ].join(" · ")));
    li.append(rank, body);
    list.appendChild(li);
  });
  if (!honored.length)
    list.appendChild(el("p", "empty", "Todavía ningún incidente tiene más de un artículo firmado."));

  /* Voces: en el orden del ranking territorial, más las colonias con firma
     que aún no tienen incidente en el ranking. */
  const voices = cred.colonia_voices || {};
  const ranked = (DATA.colonia_rank || { ranked: [] }).ranked.map((r) => r.colonia);
  const order = ranked.concat(Object.keys(voices).filter((c) => !ranked.includes(c)).sort());
  const vlist = $("#soc-voices");
  vlist.textContent = "";
  let solo = 0, silent = 0;
  order.forEach((colonia) => {
    const v = voices[colonia];
    if (!v || !v.voices.length) { silent += 1; return; }
    if (v.solo) solo += 1;
    const li = el("li", "cred");
    const body = el("div", "cred-body");
    const name = el("button", "cred-name", colonia);
    name.type = "button";
    name.title = "Ver los incidentes de " + colonia;
    name.addEventListener("click", () => focusSearch(colonia));
    body.appendChild(name);
    body.appendChild(el("p", "byline", v.voices.map(([who, n]) => `${who} (${n})`).join(" · ")));
    if (v.solo) {
      const tags = el("div", "tags");
      const t = el("span", "tag solo", "una sola voz");
      t.title = "Una sola firma cubre esta colonia — si deja de escribir, la colonia se queda sin voz en el mapa";
      tags.appendChild(t);
      body.appendChild(tags);
    }
    li.appendChild(body);
    vlist.appendChild(li);
  });
  if (!vlist.childNodes.length)
    vlist.appendChild(el("p", "empty", "Todavía ninguna colonia tiene un artículo con firma."));

  renderSocialRanking(cred.authors);

  const bits = [];
  if (solo) bits.push(`${solo} colonia${solo === 1 ? " depende" : "s dependen"} de una sola firma`);
  if (silent) bits.push(`${silent} del ranking no ${silent === 1 ? "tiene" : "tienen"} todavía ninguna firma conocida`);
  $("#soc-note").textContent =
    (bits.length ? bits.join("; ") + ". " : "") +
    "Solo firmas de prensa entran a esta capa: los registros de redes sociales viajan sin autor por diseño.";
}

/* Ranking: la tabla completa detrás de las dos pestañas anteriores. El puntaje
   pesa el trabajo que sostiene el mapa — un artículo y un incidente valen uno,
   abrir una historia vale tres, volver a ella vale dos — y se muestra con sus
   columnas a la vista para que cualquiera pueda rehacer la cuenta. */
function renderSocialRanking(authors) {
  const rows = authors
    .map((a) => [a, SOC_SCORE(a)])
    .sort((x, y) => (y[1] - x[1]) || (y[0].records - x[0].records));
  const body = $("#soc-rank-table").tBodies[0];
  body.textContent = "";
  rows.forEach(([a, score], i) => {
    const tr = el("tr");
    tr.appendChild(el("td", "num rank" + (i < 3 ? " top" : ""), String(i + 1)));

    const td = el("td");
    const link = el("button", "rowlink", a.name);
    link.type = "button";
    link.title = "Ver los incidentes que documentó";
    link.addEventListener("click", () => focusSearch(a.name));
    td.appendChild(link);
    if (a.kind === "desk") td.appendChild(el("span", "tag", " redacción"));
    tr.appendChild(td);

    tr.appendChild(el("td", null, a.outlets.map(([o]) => o).join(" · ")));
    [a.records, a.incidents, a.primicias, a.seguimientos, a.colonias.length, score]
      .forEach((n) => tr.appendChild(el("td", "num", String(n))));
    body.appendChild(tr);
  });

  $("#soc-rank-note").textContent = rows.length
    ? `${rows.length} firma${rows.length === 1 ? "" : "s"} en el ranking, redacciones incluidas. ` +
      "El puntaje ordena, no mide calidad: es una cuenta de volumen y de constancia."
    : "";
  if (!rows.length) {
    const td = el("td", "empty", "Todavía ninguna firma registrada");
    td.colSpan = 9;
    body.appendChild(el("tr")).appendChild(td);
  }
}

/* ---------------------------------------------------------------- ciclos */
function renderCycles() {
  const body = $("#cycle-table").tBodies[0];
  body.textContent = "";
  DATA.cycles.slice().reverse().forEach((c) => {
    const tr = el("tr");
    [c.cycle, c.scanned, c.qualified, c.unsure, c.excluded, c.fetched].forEach((v, i) => {
      tr.appendChild(el("td", i ? "num" : null, String(v)));
    });
    body.appendChild(tr);
  });

  const reasons = {};
  DATA.cycles.forEach((c) => c.exclusion_reasons.forEach(([code, n]) => {
    reasons[code] = (reasons[code] || 0) + n;
  }));
  const pairs = Object.entries(reasons).sort((a, b) => b[1] - a[1]);
  const max = pairs.length ? pairs[0][1] : 1;
  const box = $("#reason-bars");
  box.textContent = "";
  pairs.forEach(([code, n]) => {
    const row = el("div", "reason");
    row.appendChild(el("span", null, REASON_LABEL[code] || code.replace(/_/g, " ")));
    const track = el("span", "track");
    const fill = el("span", "fill");
    fill.style.width = (100 * n / max) + "%";
    fill.style.display = "block";
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", "n", String(n)));
    box.appendChild(row);
  });
}

/* ---------------------------------------------------------------- articles */
let artPage = 1;
const artEls = ["#a-search", "#a-bucket", "#a-category", "#a-outlet",
                "#a-from", "#a-to", "#a-sort", "#a-recorded"];

function artQuery() {
  const p = new URLSearchParams();
  const put = (k, v) => { if (v) p.set(k, v); };
  put("q", $("#a-search").value.trim());
  put("bucket", $("#a-bucket").value);
  put("category", $("#a-category").value);
  put("outlet", $("#a-outlet").value);
  put("from", $("#a-from").value);
  put("to", $("#a-to").value);
  put("sort", $("#a-sort").value);
  if ($("#a-recorded").checked) p.set("recorded", "1");
  p.set("page", String(artPage));
  p.set("per", "50");
  return p.toString();
}

async function loadArticles() {
  const list = $("#article-list");
  list.textContent = "";
  list.appendChild(el("p", "empty", "Cargando…"));
  let data;
  try {
    data = await fetchArticles(artQuery());
  } catch (err) {
    list.textContent = "";
    list.appendChild(el("p", "empty", "No se pudieron cargar los artículos: " + err.message));
    return;
  }

  // repopulate facet dropdowns, preserving the current choice
  const keep = (sel) => $(sel).value;
  const bk = keep("#a-bucket"), ct = keep("#a-category"), ot = keep("#a-outlet");
  fill($("#a-bucket"), data.facets.buckets.map(([b, n]) => ({ value: b, label: `${BUCKET_LABEL[b] || b} (${n})` })), "Cualquier grupo");
  const articleCats = orderedCategories(data.facets.categories.map(([c]) => c))
    .map((c) => {
      const hit = data.facets.categories.find(([name]) => name === c);
      return { value: c, label: `${CATEGORY_LABEL[c] || c} (${hit ? hit[1] : 0})` };
    });
  fill($("#a-category"), articleCats, "Cualquier tema del foco");
  fill($("#a-outlet"), data.facets.outlets.map(([o, n]) => ({ value: o, label: `${o} (${n})` })), "Todos los medios");
  $("#a-bucket").value = bk; $("#a-category").value = ct; $("#a-outlet").value = ot;

  const first = data.total ? (data.page - 1) * data.per + 1 : 0;
  const last = Math.min(data.page * data.per, data.total);
  const label = `${first.toLocaleString()}–${last.toLocaleString()} de ${data.total.toLocaleString()}` +
                ` · página ${data.page} de ${data.pages}`;
  $("#a-count").textContent = label;
  $("#a-count2").textContent = label;
  ["#a-prev", "#a-prev2"].forEach((s2) => { $(s2).disabled = data.page <= 1; });
  ["#a-next", "#a-next2"].forEach((s2) => { $(s2).disabled = data.page >= data.pages; });

  list.textContent = "";
  if (!data.items.length) {
    list.appendChild(el("p", "empty", "Ningún artículo coincide con estos filtros."));
    return;
  }
  data.items.forEach((r) => {
    const li = el("li", "art " + r.bucket);
    li.appendChild(el("span", "sc", String(r.score)));
    const body = el("div");
    const t = el("a", "ttl", r.title || "(untitled)");
    t.href = r.url; t.target = "_blank"; t.rel = "noopener noreferrer";
    body.appendChild(t);
    body.appendChild(el("p", "meta",
      `${r.date} · ${r.outlet}${r.author ? " · " + r.author : ""} · ${REASON_LABEL[r.reason] || r.reason}`));
    if (r.snippet) body.appendChild(el("p", "snip", "…" + r.snippet.replace(/^…|…$/g, "") + "…"));
    const tags = el("div", "tags");
    visibleCategories(r.categories).forEach((c) => tags.appendChild(el("span", "tag cat", CATEGORY_LABEL[c] || c)));
    r.signals.slice(0, 3).forEach((sg) => tags.appendChild(el("span", "tag", sg)));
    if (r.recorded) tags.appendChild(el("span", "tag rec", "con registro"));
    if (tags.childElementCount) body.appendChild(tags);
    li.appendChild(body);
    list.appendChild(li);
  });
}

function initArticles() {
  const c = DATA.corpus;
  $("#tab-articles").hidden = !c;
  if (!c) return;
  $("#art-intro").textContent =
    `${c.count.toLocaleString()} artículos sobre ${focusInfo().label}, del ${c.first} al ${c.last}. ` +
    `El puntaje y el grupo provienen del filtro de palabras clave: ordenan lo que conviene leer, ` +
    `nunca deciden que un artículo califique. «Con registro» marca los que ya tienen ficha.`;
  artEls.forEach((sel) => $(sel).addEventListener("input", () => { artPage = 1; loadArticles(); }));
  $("#a-reset").addEventListener("click", () => {
    artEls.forEach((sel) => {
      const node = $(sel);
      if (node.type === "checkbox") node.checked = false; else node.value = "";
    });
    $("#a-sort").value = "score";
    artPage = 1; loadArticles();
  });
  ["#a-prev", "#a-prev2"].forEach((s2) => $(s2).addEventListener("click", () => {
    if (artPage > 1) { artPage -= 1; loadArticles(); window.scrollTo({ top: 0, behavior: "smooth" }); }
  }));
  ["#a-next", "#a-next2"].forEach((s2) => $(s2).addEventListener("click", () => {
    artPage += 1; loadArticles(); window.scrollTo({ top: 0, behavior: "smooth" });
  }));
  loadArticles();
}

/* ---------------------------------------------------------------- screening */
function barRows(box, pairs, colorVar) {
  box.textContent = "";
  const max = pairs.length ? Math.max(...pairs.map((p) => p[1])) : 1;
  pairs.forEach(([label, n]) => {
    const row = el("div", "reason");
    row.appendChild(el("span", null, String(label).replace(/_/g, " ")));
    const track = el("span", "track"), fill = el("span", "fill");
    fill.style.width = (100 * n / max) + "%";
    fill.style.display = "block";
    if (colorVar) fill.style.background = `var(${colorVar})`;
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", "n", String(n)));
    box.appendChild(row);
  });
  if (!pairs.length) box.appendChild(el("p", "empty", "ninguno"));
}

/* ---------------------------------------------------------------- lectura */
function renderReading() {
  const sc = DATA.reading;
  $("#tab-screening").hidden = !sc;
  if (!sc) return;

  const w = sc.window || {};
  $("#screen-intro").textContent =
    `El corpus visible tiene ${sc.total.toLocaleString()} artículos sobre ${focusInfo().label}, ` +
    `del ${w.after || "?"} al ${w.before || "?"}. ` +
    `Todos se leen completos: no se descarta ninguno sin leer. La puntuación del vocabulario ` +
    `sólo fija el orden de lectura, nunca si un artículo califica. ` +
    (sc.unread
      ? `Faltan ${sc.unread.toLocaleString()} por leer, así que las cifras del resto del panel ` +
        `describen lo leído hasta ahora y nada más.`
      : `La lectura del corpus está completa.`);

  const stats = $("#screen-stats");
  stats.textContent = "";
  [[sc.read, "leídos y triados", "--series-1"],
   [sc.unread, "aún sin leer", "--series-3"],
   [sc.pct_read + "%", "del corpus leído", "--series-2"]].forEach(([value, label, color]) => {
    const box = el("div", "stat");
    const n = el("span", "stat-n", typeof value === "number" ? value.toLocaleString() : value);
    n.style.color = `var(${color})`;
    box.append(n, el("span", "stat-l", label));
    stats.appendChild(box);
  });

  const tierRows = ["priority_high", "priority_medium", "priority_low"]
    .map((k) => [`${BUCKET_LABEL[k]} — faltan ${(sc.tiers_unread[k] || 0).toLocaleString()}`,
                 sc.tiers[k] || 0]);
  barRows($("#screen-reasons"), tierRows, "--series-2");
  barRows($("#screen-outlets"), sc.unread_by_outlet, "--series-3");
  barRows($("#screen-cats"), sc.categories_in_corpus.map(([c, n]) => [CATEGORY_LABEL[c] || c, n]), "--series-2");

  const aud = $("#audits");
  aud.textContent = "";
  if (!DATA.audits.length) {
    aud.appendChild(el("p", "empty", "Aún no se ha hecho ninguna auditoría de calidad. Muestrea registros con sample.py records."));
  }
  DATA.audits.forEach((a) => {
    const item = el("div", "item" + (a.accuracy_pct < 90 ? " gap" : ""));
    item.appendChild(el("strong", null, `${a.kind}: ${a.accuracy_pct}% de acierto`));
    item.appendChild(el("span", "byline", ` · ${a.checked} revisados, ${a.misses} omitidos`));
    if (a.note) item.appendChild(el("p", "why", a.note));
    aud.appendChild(item);
  });

  const body = $("#unread-table").tBodies[0];
  body.textContent = "";
  sc.next_to_read.forEach((r) => {
    const tr = el("tr");
    tr.appendChild(el("td", null, r.article_date));
    tr.appendChild(el("td", null, r.source_outlet));
    const td = el("td");
    const a = el("a", null, r.title);
    a.href = r.article_url; a.target = "_blank"; a.rel = "noopener noreferrer";
    td.appendChild(a);
    tr.appendChild(td);
    tr.appendChild(el("td", "num", String(r.score)));
    tr.appendChild(el("td", null, BUCKET_LABEL[r.bucket] || r.bucket));
    body.appendChild(tr);
  });
}

/* ---------------------------------------------------------------- aprendizaje */
function chipList(values) {
  const ul = el("ul", "chips");
  if (!values.length) ul.appendChild(el("li", null, "ninguno aún"));
  values.forEach((v) => ul.appendChild(el("li", null, v)));
  return ul;
}

function renderLearning() {
  const gaz = $("#gazetteer");
  gaz.textContent = "";
  [["streets", "Calles"], ["colonias", "Colonias"], ["landmarks", "Puntos de referencia"]].forEach(([key, label]) => {
    gaz.appendChild(el("p", "kind", label));
    gaz.appendChild(chipList(DATA.gazetteer[key] || []));
  });

  const cov = $("#coverage");
  cov.textContent = "";
  const heard = (DATA.coverage.colonias_heard_from || []);
  cov.appendChild(el("p", "kind", `Colonias de las que se ha sabido (${heard.length})`));
  cov.appendChild(chipList(heard));
  if (!DATA.coverage.colonia_master_list) {
    const gap = el("div", "item gap");
    gap.appendChild(el("strong", null, "El análisis de puntos ciegos está bloqueado"));
    gap.appendChild(el("p", "why", DATA.coverage.colonia_master_list_note || ""));
    cov.appendChild(gap);
  }

  const vocab = $("#vocab");
  vocab.textContent = "";
  (DATA.vocabulary.watch_list || []).forEach((w) => {
    const item = el("div", "item");
    const head = el("strong", null, w.term);
    item.appendChild(head);
    item.appendChild(el("span", "byline", w.promoted ? " · promovido a activo" : " · en observación"));
    item.appendChild(el("p", "why", w.why));
    vocab.appendChild(item);
  });
  if (!vocab.childElementCount) vocab.appendChild(el("p", "empty", "Todavía no hay términos en observación."));

  const sources = $("#sources");
  sources.textContent = "";
  (DATA.candidate_sources.candidates || []).forEach((s) => {
    const item = el("div", "item");
    item.appendChild(el("strong", null, s.name));
    item.appendChild(el("span", "byline", " · " + s.kind));
    item.appendChild(el("p", "why", s.why));
    item.appendChild(el("p", "pend", SOURCE_STATUS_LABEL[s.status] || s.status.replace(/_/g, " ")));
    sources.appendChild(item);
  });
  if (!sources.childElementCount) sources.appendChild(el("p", "empty", "No hay fuentes candidatas registradas."));
}

load();
