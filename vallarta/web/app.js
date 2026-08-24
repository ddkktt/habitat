/* Tablero de quejas de Puerto Vallarta — sin dependencias ni paso de compilación.
   Todos los datos vienen de /api/data, que relee los archivos JSON del disco cada vez. */
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
const STATUS_LABEL = {
  new_complaint: "queja nueva", ongoing: "en curso", failed_repair: "reparación fallida",
  resolved: "resuelto", unclear: "sin definir",
};
const CERTAINTY_LABEL = { exact: "exacta", approximate: "aproximada", none: "sin ubicación" };
const CERTAINTY_COLOR = { exact: "--series-1", approximate: "--series-2", none: "--series-3" };
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
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("is-on", t === tab));
    document.querySelectorAll(".panel").forEach((p) => { p.hidden = p.id !== tab.dataset.panel; });
  });
});

/* ---------------------------------------------------------------- carga */
async function load() {
  $("#status").textContent = "Cargando…";
  $("#status").classList.remove("error");
  try {
    const resp = await fetch("/api/data", { cache: "no-store" });
    const payload = await resp.json();
    if (payload.error) throw new Error(payload.error);
    DATA = payload;
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
  $("#s-incidents").textContent = t.incidents;
  $("#s-records").textContent = t.records;
  $("#s-located").textContent = t.located_share + "%";
  $("#s-unsure").textContent = t.unsure;

  const cycles = DATA.cycles;
  if (cycles.length) {
    const last = cycles[cycles.length - 1];
    $("#source-line").textContent =
      `${last.scanned} artículos revisados en el ciclo ${last.cycle} · ${t.incidents} incidentes registrados en total`;
  }

  renderCertainty(t.certainty, t.records);
  initMapSection();
  buildFilters();
  renderIncidents();
  renderColonias();
  renderCredits();
  renderCycles();
  renderLearning();
  renderReading();
  initArticles();
  $("#report-md").textContent = DATA.report ? DATA.report.markdown : "Todavía no hay informe.";
}

function renderCertainty(certainty, total) {
  const bar = $("#certainty-bar"), key = $("#certainty-key");
  bar.textContent = ""; key.textContent = "";
  ["exact", "approximate", "none"].forEach((level) => {
    const n = certainty[level] || 0;
    if (n) {
      const seg = el("span");
      seg.style.width = (100 * n / Math.max(total, 1)) + "%";
      seg.style.background = `var(${CERTAINTY_COLOR[level]})`;
      bar.appendChild(seg);
    }
    const item = el("span", null);
    const swatch = el("i");
    swatch.style.background = `var(${CERTAINTY_COLOR[level]})`;
    item.append(swatch, document.createTextNode(`${CERTAINTY_LABEL[level]} ${n}`));
    key.appendChild(item);
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

function mapAgg() {
  const agg = new Map();
  let noloc = 0;
  DATA.incidents.forEach((inc) => {
    if (mapState.cat && !inc.categories.includes(mapState.cat)) return;
    if (mapState.status && inc.status !== mapState.status) return;
    if (mapState.month !== null && monthKey(inc.first_article_date) !== mapMonths[mapState.month]) return;
    if (!inc.colonia) { noloc += 1; return; }
    let a = agg.get(inc.colonia);
    if (!a) agg.set(inc.colonia, a = { n: 0, cats: {} });
    a.n += 1;
    inc.categories.forEach((c) => { a.cats[c] = (a.cats[c] || 0) + 1; });
  });
  return { agg, noloc };
}

/* Lleva al panel de incidentes filtrado por un texto: una colonia desde el
   mapa o el ranking, o una firma desde el panel de colaboradores. */
function focusSearch(query) {
  $("#f-reset").click();
  $("#f-search").value = query;
  renderIncidents();
  document.querySelector('.tab[data-panel="p-incidents"]').click();
  document.getElementById("p-incidents").scrollIntoView({ behavior: "smooth" });
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
    inc.categories.forEach((c) => cats.add(c));
    statuses.add(inc.status);
  });
  /* fauna se ofrece siempre: elegirla enciende la capa de zonas con presencia
     conocida de cocodrilos aunque todavía haya pocos (o cero) incidentes */
  cats.add("wildlife");
  const keepCat = $("#m-category").value, keepSt = $("#m-status").value;
  fill($("#m-category"), [...cats].sort().map((c) => ({ value: c, label: CATEGORY_LABEL[c] || c })), "Todas las categorías");
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
  const { agg, noloc } = mapAgg();
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
    (mapState.cat ? " · " + (CATEGORY_LABEL[mapState.cat] || mapState.cat) : "") +
    (mapState.status ? " · " + (STATUS_LABEL[mapState.status] || mapState.status) : "");
  $("#m-label").textContent = `${total} incidentes con colonia · ${periodo}`;

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

  $("#m-noloc").textContent = noloc
    ? `${noloc} incidente${noloc === 1 ? "" : "s"} de este filtro no traen colonia en el artículo, así que no pueden dibujarse.`
    : "Todos los incidentes de este filtro traen colonia.";
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
   Es conocimiento de fondo para leer el mapa — nunca entra a ningún conteo —
   y aparece cuando algún filtro de categoría está en fauna: así un incidente
   real de cocodrilo se dibuja encima de la zona donde se esperaba. */
function updateCrocZones() {
  if (!DATA) return;
  const zones = (DATA.context_zones || {}).zones || [];
  const on = zones.length > 0 &&
    (mapState.cat === "wildlife" || $("#f-category").value === "wildlife");

  if (ZONE_LAYER) {
    ZONE_LAYER.clearLayers();
    if (on) {
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
  mapNote.hidden = !on;
  if (on) {
    mapNote.textContent = "🐊 Zona punteada = presencia conocida de cocodrilos (esteros y desembocaduras de ríos; " +
      "contexto local mantenido a mano en state/context_zones.json). Es fondo para leer el mapa, no incidentes reportados.";
  }

  const ctx = $("#croc-context");
  const listOn = zones.length > 0 && $("#f-category").value === "wildlife";
  ctx.hidden = !listOn;
  ctx.textContent = "";
  if (listOn) {
    ctx.appendChild(el("p", "kind", "🐊 Contexto: zonas con presencia conocida de cocodrilos (punteadas en el mapa)"));
    zones.forEach((z) => {
      const row = el("p");
      row.appendChild(el("b", null, z.name));
      row.append(document.createTextNode(" — " + z.note));
      ctx.appendChild(row);
    });
  }
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
    inc.categories.forEach((c) => cats.add(c));
    statuses.add(inc.status);
    inc.records.forEach((r) => outlets.add(r.source_outlet));
  });
  cats.add("wildlife"); /* siempre presente: enciende la capa de zonas de cocodrilos */
  fill($("#f-category"), [...cats].sort().map((c) => ({ value: c, label: CATEGORY_LABEL[c] || c })), "Todas las categorías");
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
  if (cat && !inc.categories.includes(cat)) return false;
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
  inc.categories.forEach((c) => tags.appendChild(el("span", "tag cat", CATEGORY_LABEL[c] || c)));
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
    tr.appendChild(el("td", null, r.categories.slice(0, 2)
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
      a.categories.slice(0, 3).forEach(([c, n]) =>
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
    const resp = await fetch("/api/articles?" + artQuery(), { cache: "no-store" });
    data = await resp.json();
    if (data.error) throw new Error(data.error);
  } catch (err) {
    list.textContent = "";
    list.appendChild(el("p", "empty", "No se pudieron cargar los artículos: " + err.message));
    return;
  }

  // repopulate facet dropdowns, preserving the current choice
  const keep = (sel) => $(sel).value;
  const bk = keep("#a-bucket"), ct = keep("#a-category"), ot = keep("#a-outlet");
  fill($("#a-bucket"), data.facets.buckets.map(([b, n]) => ({ value: b, label: `${BUCKET_LABEL[b] || b} (${n})` })), "Cualquier grupo");
  fill($("#a-category"), data.facets.categories.map(([c, n]) => ({ value: c, label: `${CATEGORY_LABEL[c] || c} (${n})` })), "Cualquier categoría");
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
    r.categories.forEach((c) => tags.appendChild(el("span", "tag cat", CATEGORY_LABEL[c] || c)));
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
    `${c.count.toLocaleString()} artículos recopilados, del ${c.first} al ${c.last}. ` +
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
    `El corpus tiene ${sc.total.toLocaleString()} artículos del ${w.after || "?"} al ${w.before || "?"}. ` +
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
