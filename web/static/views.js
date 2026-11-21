"use strict";
/* LV-Prüfstand: the views "Bauwerk", "Einzel-LV", "Live-Prüfung", "Vergleich" and "Messung".
   app.js owns the page state and calls LVViews.render(view, data) when one of these views is
   shown; data is the answer of /api/findings. Every text from a data file is put into the page
   as text only, never as HTML. No answer of the server carries a unit price or a total. */
(function () {
  const TYPE = { double_assignment: "Doppelt ausgeschrieben", contradiction: "Widerspruch", gap: "Lücke" };
  const SEVERITY = { high: "hoch", medium: "mittel", info: "Hinweis" };
  const STATUS = { confirmed: "bestätigt", rejected: "verworfen", unclear: "unklar", open: "offen" };
  const KIND = { normal: "", optional: "Bedarfsposition", alternative: "Wahlposition", lump_sum: "Pauschale",
    preliminary_note: "Vorbemerkung", heading: "Abschnitt" };
  const FORMAT = { gaeb90: "GAEB 90", gaebxml: "GAEB DA XML", pdf: "PDF" };
  const STAGE = { "83": "Ausschreibung (83)", "84": "Angebot (84)", "86": "Auftrag (86)", anfrage: "Anfrage" };
  const CHECK = {
    B1: "Menge × Einheitspreis = Gesamtbetrag", B2: "Zwischensummen und Gesamtsumme",
    B3: "Positionsnummern: Reihenfolge, Lücken, doppelte", B4: "Wiederholte Position",
    B5: "Einheit fehlt, unbekannt oder abweichend", B6: "Menge fehlt, null, negativ oder zehnfach abweichend",
    B7: "Ungewöhnlicher Einheitspreis (nur Frage)", B8: "Leere oder sehr kurze Beschreibung",
    B9: "Anteil der Pauschalpositionen", B10: "Bedarfs- und Wahlpositionen",
    B11: "Unbestimmte Formulierungen", B12: "Fabrikat ohne «oder gleichwertig»",
  };
  const cache = {};
  const local = { cell: null, lv: null, live: null };

  const $ = (id) => document.getElementById(id);

  function el(tag, props) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else node.setAttribute(key, value);
    }
    for (let i = 2; i < arguments.length; i++) {
      const child = arguments[i];
      if (child === null || child === undefined) continue;
      node.append(child);
    }
    return node;
  }

  function label(map, value) {
    if (value === null || value === undefined || value === "") return "nicht angegeben";
    return Object.prototype.hasOwnProperty.call(map, value) ? map[value] : value;
  }

  function number(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "";
    return value.toLocaleString("de-DE", { maximumFractionDigits: 3 });
  }

  function seconds(value) {
    return typeof value === "number" ? value.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " s" : "";
  }

  async function getJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || "Fehler " + response.status);
    return body;
  }

  async function load(key, url, force) {
    if (!force && cache[key]) return cache[key];
    cache[key] = await getJSON(url);
    return cache[key];
  }

  function message(root, text, kind) {
    root.replaceChildren(el("p", { class: "message" + (kind === "error" ? " error" : ""), text: text }));
  }

  function tile(numberText, text, extra) {
    return el("div", { class: "tile" + (extra ? " " + extra : "") },
      el("span", { class: "number", text: String(numberText) }), el("span", { class: "label", text: text }));
  }

  function reviewStatus(finding) {
    const status = finding && finding.review ? finding.review.status : null;
    return status === "confirmed" || status === "rejected" || status === "unclear" ? status : "open";
  }

  function shortDoc(doc) {
    return String(doc || "").replace(/^LV_/, "");
  }

  // ---- Bauwerk -------------------------------------------------------------

  async function renderBauwerk(data) {
    const root = $("bauwerk-root");
    let matrix;
    try {
      matrix = await load("matrix", "/api/matrix", true);
    } catch (error) {
      message(root, "Die Matrix konnte nicht geladen werden: " + error.message, "error");
      return;
    }
    const findings = data ? data.findings : [];
    const byId = {};
    for (const finding of findings) byId[finding.id] = finding;
    const counters = data ? data.counters.all : { count: 0, confirmed: 0, rejected: 0, unclear: 0, open: 0 };
    const tiles = el("div", { class: "tiles" },
      tile(matrix.lists.length, "Leistungsverzeichnisse"),
      tile(matrix.positions.toLocaleString("de-DE"), "Positionen"),
      tile(counters.count, "Funde zwischen und in den Listen"),
      tile(counters.confirmed + " / " + counters.rejected + " / " + counters.open,
        "bestätigt / verworfen / offen", "review"));

    const cells = {};
    for (const cell of matrix.cells) cells[cell.a + "|" + cell.b] = cell;
    const lists = matrix.lists;
    const table = el("table", { class: "matrix", "aria-label": "Matrix der Gewerke" });
    const head = el("tr", {}, el("th", { class: "corner", text: "" }));
    for (const entry of lists) {
      head.append(el("th", { class: "col", title: entry.doc + " " + entry.trade },
        el("span", { text: shortDoc(entry.doc) })));
    }
    table.append(el("thead", {}, head));
    const body = el("tbody");
    lists.forEach((row, i) => {
      const tr = el("tr", {}, el("th", { class: "row", title: row.positions + " Positionen" },
        el("span", { class: "doc", text: row.doc }), el("span", { class: "trade", text: row.trade })));
      lists.forEach((col, j) => {
        if (j < i) { tr.append(el("td", { class: "off" })); return; }
        const cell = cells[row.doc + "|" + col.doc];
        if (!cell) { tr.append(el("td", { class: j === i ? "diag" : "" })); return; }
        const shown = cell.findings.filter((id) => byId[id]);
        const held = shown.filter((id) => !byId[id].k3_pass).length;
        const confirmed = shown.filter((id) => reviewStatus(byId[id]) === "confirmed").length;
        const classes = ["cell"];
        if (shown.length) classes.push("has", "sev-" + (cell.severity || "none"));
        else classes.push("handover");
        if (shown.length && held === shown.length) classes.push("held");
        if (confirmed) classes.push("confirmed");
        if (local.cell === cell.a + "|" + cell.b) classes.push("active");
        const title = [row.doc + " × " + col.doc];
        if (shown.length) title.push(shown.length + " Fund(e)");
        if (cell.handovers.length) title.push("Übergabe: " + cell.handovers.join("; "));
        const td = el("td", { class: classes.join(" "), title: title.join(" · "), tabindex: "0",
          "data-cell": cell.a + "|" + cell.b, "data-findings": shown.join(" ") }, shown.length ? String(shown.length) : "");
        const open = () => { local.cell = cell.a + "|" + cell.b; renderBauwerk(data); };
        td.addEventListener("click", open);
        td.addEventListener("keydown", (event) => { if (event.key === "Enter") open(); });
        tr.append(td);
      });
      body.append(tr);
    });
    table.append(body);

    const legend = el("div", { class: "legend" },
      el("span", { class: "key sev-high", text: "hoch" }), el("span", { class: "key sev-medium", text: "mittel" }),
      el("span", { class: "key sev-info", text: "Hinweis" }), el("span", { class: "key handover", text: "Übergabe ohne Fund" }),
      el("span", { class: "key held", text: "nur zurückgehaltene Funde" }),
      el("span", { class: "hint", text: "Zahl = Funde der Zelle. Klick auf eine Zelle zeigt ihre Funde." }));

    const panel = el("aside", { class: "cell-panel" });
    const chosen = local.cell ? cells[local.cell] : null;
    if (!chosen) {
      panel.append(el("h3", { text: "Zwischen den Dokumenten" }),
        el("p", { text: "Jede Zeile und Spalte ist ein Leistungsverzeichnis. Eine farbige Zelle heißt: " +
          "Zwischen diesen beiden Listen steht ein Fund. Die Diagonale zeigt Funde innerhalb einer Liste." }),
        el("p", { text: matrix.handovers.length ? matrix.handovers.length + " Übergaben zwischen Gewerken sind " +
          "aus den Listen belegt (graue Zellen ohne Zahl)." : "" }));
    } else {
      const a = lists.find((entry) => entry.doc === chosen.a) || { doc: chosen.a, trade: "" };
      const b = lists.find((entry) => entry.doc === chosen.b) || { doc: chosen.b, trade: "" };
      panel.append(el("h3", { text: a.doc + (a.trade ? " · " + a.trade : "") +
        (chosen.a === chosen.b ? "" : "  ×  " + b.doc + (b.trade ? " · " + b.trade : "")) }));
      if (chosen.handovers.length) panel.append(el("p", { class: "muted", text: "Übergabe: " + chosen.handovers.join("; ") }));
      const ids = chosen.findings.filter((id) => byId[id]);
      if (!ids.length) panel.append(el("p", { text: "Kein Fund in dieser Zelle." }));
      for (const id of ids) {
        const finding = byId[id];
        const status = reviewStatus(finding);
        const button = el("button", { type: "button", class: "cell-finding" },
          el("span", { class: "row" }, el("strong", { text: id }),
            el("span", { class: "badge st-" + status, text: STATUS[status] })),
          el("span", { text: label(TYPE, finding.type) + " · " + label(SEVERITY, finding.severity) +
            (finding.k3_pass ? "" : " · zurückgehalten") }),
          el("span", { class: "question", text: finding.question_de || "" }));
        button.addEventListener("click", () => window.LV.openFinding(id));
        panel.append(button);
      }
    }
    root.replaceChildren(el("div", { class: "bauwerk" }, el("div", { class: "matrix-scroll" }, table),
      el("div", { class: "bauwerk-side" }, tiles, legend, panel)));
  }

  // ---- item tables (Einzel-LV and Live-Prüfung) -----------------------------------

  function marksByItem(findings) {
    const marks = {};
    for (const finding of findings) {
      for (const itemNo of finding.item_nos || []) {
        (marks[itemNo] = marks[itemNo] || []).push(finding);
      }
    }
    return marks;
  }

  function itemTable(rows, findings, total) {
    const marks = marksByItem(findings);
    const table = el("table", { class: "items" });
    table.append(el("thead", {}, el("tr", {},
      el("th", { text: "Pos." }), el("th", { text: "Kurztext" }), el("th", { class: "num", text: "Menge" }),
      el("th", { text: "Einheit" }), el("th", { text: "Seite" }), el("th", { text: "Grundprüfungen" }))));
    const body = el("tbody");
    for (const row of rows) {
      const kind = KIND[row.kind] || "";
      const isHead = row.kind === "heading" || row.kind === "preliminary_note";
      const found = isHead ? [] : (marks[row.item_no] || []);
      const cell = el("td", { class: "marks" });
      for (const finding of found) {
        cell.append(el("span", { class: "mark sev-" + (finding.severity || ""), title: (finding.explanation_de || "") +
          (finding.question_de ? "\nFrage: " + finding.question_de : ""), text: finding.check }));
      }
      body.append(el("tr", { class: isHead ? "head-row" : found.length ? "flagged" : "" },
        el("td", { class: "no", text: row.item_no || "" }),
        el("td", {}, kind ? el("span", { class: "kind", text: kind }) : null, document.createTextNode(row.short_text || "")),
        el("td", { class: "num", text: number(row.quantity) }), el("td", { text: row.unit || "" }),
        el("td", { text: row.page === null || row.page === undefined ? "" : String(row.page) }), cell));
    }
    table.append(body);
    const wrap = el("div", { class: "items-wrap" }, table);
    if (total > rows.length) wrap.append(el("p", { class: "muted", text: "Gezeigt: " + rows.length + " von " + total + " Einträgen." }));
    return wrap;
  }

  function findingList(findings, total) {
    const list = el("div", { class: "base-findings" });
    for (const finding of findings) {
      list.append(el("div", { class: "base-finding" },
        el("span", { class: "badge sev-" + (finding.severity || ""), text: finding.check + " · " + label(SEVERITY, finding.severity) }),
        el("span", { class: "where", text: "Pos. " + (finding.item_nos || []).join(", ") }),
        el("span", { text: finding.explanation_de || "" })));
    }
    if (total > findings.length) list.append(el("p", { class: "muted", text: "Gezeigt: " + findings.length + " von " + total + " Hinweisen." }));
    return list;
  }

  // ---- Einzel-LV -------------------------------------------------------------------

  async function renderEinzel() {
    const root = $("einzel-root");
    let lists;
    try {
      lists = await load("lv", "/api/lv", true);
    } catch (error) {
      message(root, "Die Listen konnten nicht geladen werden: " + error.message, "error");
      return;
    }
    if (!lists.lists.length) { message(root, "Keine Liste gelesen."); return; }
    const select = el("select", { id: "lv-select", "aria-label": "Leistungsverzeichnis wählen" });
    for (const entry of lists.lists) {
      const option = el("option", { value: entry.doc, text: entry.doc + (entry.trade ? " · " + entry.trade : "") +
        " (" + entry.positions + " Positionen, " + entry.base_findings + " Hinweise)" });
      select.append(option);
    }
    local.lv = local.lv && lists.lists.some((e) => e.doc === local.lv) ? local.lv : lists.lists[0].doc;
    select.value = local.lv;
    const detail = el("div", { class: "lv-detail" });
    select.addEventListener("change", () => { local.lv = select.value; showDoc(); });
    const note = lists.base_findings_file ? null :
      el("p", { class: "message", text: "Die Grundprüfungen dieses Projekts sind noch nicht gelaufen (python -m pipeline.run)." });
    root.replaceChildren(...[el("div", { class: "lv-bar" }, el("label", { class: "field" }, "Leistungsverzeichnis", select)), note, detail]
      .filter(Boolean));

    async function showDoc() {
      detail.replaceChildren(el("p", { text: "Wird geladen …" }));
      try {
        const doc = await getJSON("/api/lv/" + encodeURIComponent(local.lv));
        const tiles = el("div", { class: "tiles" },
          tile(doc.rows.filter((r) => r.kind !== "heading" && r.kind !== "preliminary_note").length, "Positionen"),
          tile(doc.findings_total, "Hinweise der Grundprüfungen B1–B12"));
        const checks = el("p", { class: "muted", text: doc.checks.map((c) => c.check + ": " + c.findings).join(" · ") ||
          "Keine Hinweise der Grundprüfungen." });
        detail.replaceChildren(tiles, checks, itemTable(doc.rows, doc.findings, doc.rows_total));
      } catch (error) {
        message(detail, "Die Liste konnte nicht geladen werden: " + error.message, "error");
      }
    }
    showDoc();
  }

  // ---- Live-Prüfung ------------------------------------------------------------------

  function renderLive() {
    const root = $("live-root");
    if (root.dataset.ready) return;
    root.dataset.ready = "1";
    const input = el("input", { type: "file", id: "live-file", accept: ".d83,.d84,.d86,.x83,.x84,.x86,.D83,.D84,.D86,.X83,.X84,.X86" });
    const chosen = el("span", { class: "chosen", text: "Keine Datei gewählt." });
    const zone = el("label", { class: "drop", for: "live-file" },
      el("strong", { text: "GAEB-Datei hierher ziehen oder klicken" }),
      el("span", { text: "GAEB 90 (.D83, .D84, .D86) oder GAEB DA XML (.X83, .X84, .X86). Die Datei wird nur in " +
        "dieser Anwendung auf diesem Rechner gelesen und nicht gespeichert." }), chosen, input);
    const result = el("div", { id: "live-result", class: "live-result" });
    root.replaceChildren(zone, result);
    const send = async (file) => {
      if (!file) return;
      chosen.textContent = "Gewählt: " + file.name;
      result.replaceChildren(el("p", { text: file.name + " wird gelesen und geprüft …" }));
      try {
        const response = await fetch("/api/live", { method: "POST", body: file,
          headers: { "X-File-Name": encodeURIComponent(file.name), "Content-Type": "application/octet-stream" } });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || "Fehler " + response.status);
        showLive(result, body);
      } catch (error) {
        message(result, error.message, "error");
      }
    };
    input.addEventListener("change", () => send(input.files[0]));
    zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("over");
      send(event.dataTransfer.files[0]);
    });
  }

  function showLive(root, answer) {
    const re = answer.recalculation;
    const tiles = el("div", { class: "tiles" },
      tile(answer.items, "Positionen gelesen"),
      tile(seconds(answer.seconds.read), "Lesen"),
      tile(seconds(answer.seconds.checks), "12 Grundprüfungen"),
      tile(re.priced ? re.equal + " / " + re.priced : "–", re.priced ? "Menge × EP = GP stimmt" : "keine Preise in der Datei",
        re.priced && re.not_equal === 0 ? "ok" : ""));
    const facts = el("p", { class: "muted", text: answer.file + " · " + label(FORMAT, answer.format) + " · " +
      label(STAGE, answer.stage) + " · " + answer.headings + " Abschnitte · " + answer.notes + " Vorbemerkungen · " +
      answer.unparsed + " nicht gelesene Zeilen · " + answer.warnings_total + " Warnungen" +
      (re.priced ? " · Nachrechnung: " + re.equal + " gleich, " + re.not_equal + " ungleich, " + re.no_quantity +
        " ohne Menge (Preise werden nur gezählt, nicht gezeigt)" : "") });
    const checks = el("table", { class: "checks" });
    checks.append(el("thead", {}, el("tr", {}, el("th", { text: "Prüfung" }), el("th", { text: "Was" }),
      el("th", { class: "num", text: "Hinweise" }))));
    const body = el("tbody");
    for (const check of answer.checks) {
      body.append(el("tr", { class: check.not_applicable ? "na" : "" }, el("td", { text: check.check }),
        el("td", { text: CHECK[check.check] || check.title }),
        el("td", { class: "num", text: check.not_applicable ? "nicht anwendbar" : String(check.findings) })));
    }
    checks.append(body);
    const parts = [tiles, facts, el("div", { class: "live-grid" }, checks, findingList(answer.findings, answer.findings_total))];
    if (answer.warnings.length) parts.push(el("details", {}, el("summary", { text: "Warnungen des Lesers" }),
      el("ul", {}, ...answer.warnings.map((w) => el("li", { text: w })))));
    parts.push(el("h3", { text: "Positionen der Datei" }), itemTable(answer.rows, answer.findings, answer.rows_total));
    root.replaceChildren(...parts);
  }

  // ---- Vergleich ---------------------------------------------------------------------

  async function renderVergleich() {
    const root = $("vergleich-root");
    let answer;
    try {
      answer = await load("diff", "/api/diff");
    } catch (error) {
      message(root, error.message);
      return;
    }
    const h = answer.hypothesis;
    const sections = h.sections.map((s) => s.item_no + " " + s.title).join(", ");
    const hypo = el("section", { class: "card wide" },
      el("h3", { text: "Ausschreibung gegen Auftrag: 8209.003" }),
      el("div", { class: "tiles" }, tile(h.tendered, "ausgeschrieben"), tile(h.ordered, "beauftragt"),
        tile(h.added.count, "kamen hinzu", "added"), tile(h.removed, "entfallen"), tile(h.renumbered, "umnummeriert")),
      el("p", { text: "Ergebnis: " + h.verdict + ". Hinzugekommen: " + h.added.shown.join(", ") +
        (h.added.count > h.added.shown.length ? " …" : "") + "." }),
      el("p", { class: "muted", text: (sections ? "Sie stehen nur im Auftrag, in: " + sections + ". " : "") +
        (h.zero_quantity ? "Der Auftrag führt sie mit Menge 0 und ohne Einheit." : "") }));
    const stage = el("table", { class: "diff" });
    stage.append(el("thead", {}, el("tr", {}, el("th", { text: "Stufen (früher gegen später)" }), el("th", { class: "num", text: "A" }),
      el("th", { class: "num", text: "B" }), el("th", { class: "num", text: "in beiden" }), el("th", { class: "num", text: "hinzu" }),
      el("th", { class: "num", text: "entfallen" }), el("th", { class: "num", text: "Menge geändert" }),
      el("th", { class: "num", text: "Preis ungleich" }))));
    const stageBody = el("tbody");
    const twin = el("table", { class: "diff" });
    twin.append(el("thead", {}, el("tr", {}, el("th", { text: "Zwillinge (dieselbe Liste, zwei Formate)" }),
      el("th", { class: "num", text: "Positionen" }), el("th", { class: "num", text: "in beiden" }),
      el("th", { class: "num", text: "Menge gleich" }), el("th", { class: "num", text: "Einheit gleich" }),
      el("th", { class: "num", text: "EP / GP gleich" }), el("th", { text: "Ergebnis" }))));
    const twinBody = el("tbody");
    const ratio = (field) => field && field.compared ? field.equal + " / " + field.compared : "–";
    for (const pair of answer.pairs) {
      if (pair.stage) {
        stageBody.append(el("tr", {}, el("td", { text: pair.title }), el("td", { class: "num", text: String(pair.a.items) }),
          el("td", { class: "num", text: String(pair.b.items) }), el("td", { class: "num", text: String(pair.both) }),
          el("td", { class: "num", text: String(pair.stage.added.count) }), el("td", { class: "num", text: String(pair.stage.removed.count) }),
          el("td", { class: "num", text: pair.fields.quantity && pair.fields.quantity.compared ? String(pair.stage.changed.quantity) : "–" }),
          el("td", { class: "num", text: (pair.fields.unit_price && pair.fields.unit_price.compared) ? String(pair.stage.changed.price) : "–" })));
      } else {
        const prices = pair.fields.unit_price && pair.fields.unit_price.compared ? ratio(pair.fields.unit_price) + " · " + ratio(pair.fields.total) : "–";
        twinBody.append(el("tr", {}, el("td", { text: pair.title }), el("td", { class: "num", text: pair.a.items + " / " + pair.b.items }),
          el("td", { class: "num", text: String(pair.both) }), el("td", { class: "num", text: ratio(pair.fields.quantity) }),
          el("td", { class: "num", text: ratio(pair.fields.unit) }), el("td", { class: "num", text: prices }),
          el("td", { text: pair.verdict || "" })));
      }
    }
    stage.append(stageBody);
    twin.append(twinBody);
    const titles = el("table", { class: "diff" });
    titles.append(el("thead", {}, el("tr", {}, el("th", { text: "PDF ohne Leser: Titel der GAEB-Liste im PDF" }),
      el("th", { class: "num", text: "suchbar" }), el("th", { class: "num", text: "gefunden" }),
      el("th", { class: "num", text: "in Reihenfolge" }), el("th", { text: "Ergebnis" }))));
    const titleBody = el("tbody");
    for (const t of answer.titles) {
      titleBody.append(el("tr", { class: t.role === "control" ? "na" : "" },
        el("td", { text: t.pdf + " ↔ " + t.list + (t.role === "control" ? " (Gegenprobe)" : t.role === "order" ? " (Auftrag)" : "") }),
        el("td", { class: "num", text: String(t.searchable) }), el("td", { class: "num", text: String(t.found) }),
        el("td", { class: "num", text: String(t.in_order) }), el("td", { text: t.verdict || "" })));
    }
    titles.append(titleBody);
    root.replaceChildren(hypo, el("section", { class: "card wide" }, stage), el("section", { class: "card wide" }, twin),
      el("section", { class: "card wide" }, titles),
      el("p", { class: "muted", text: "Gezählt per Code (pipeline/diff). Preise werden nur als gleich oder ungleich gezählt, nie gezeigt." }));
  }

  // ---- Messung -------------------------------------------------------------------------

  async function renderMessung() {
    const root = $("messung-root");
    let answer;
    try {
      answer = await load("bench", "/api/bench");
    } catch (error) {
      message(root, error.message, "error");
      return;
    }
    const table = el("table", { class: "bench" });
    table.append(el("thead", {}, el("tr", {}, el("th", { text: "Nr." }), el("th", { text: "Messung" }),
      el("th", { text: "Ergebnis" }), el("th", { text: "Schwelle (vorher festgelegt)" }), el("th", { text: "eingehalten" }))));
    const body = el("tbody");
    for (const row of answer.rows) {
      body.append(el("tr", {}, el("td", { class: "no", text: row.id }), el("td", { text: row.name }),
        el("td", { text: row.result }), el("td", { text: row.threshold }),
        el("td", {}, el("span", { class: "met met-" + row.met.replace(/\s+/g, "-"), text: row.met_de }))));
    }
    table.append(body);
    root.replaceChildren(
      el("p", { class: "muted", text: "Messlauf vom " + String(answer.measured_at || "").replace("T", " ") +
        ". Die Schwellen standen vor dem ersten Lauf fest (docs/PREREG.md). Jedes Ergebnis steht, wie es herauskam, " +
        "auch unter der Schwelle. M7 zählt Fehler, die wir selbst eingebaut haben." }),
      table);
  }

  window.LVViews = {
    names: ["bauwerk", "einzel", "live", "vergleich", "messung"],
    render(view, data) {
      if (view === "bauwerk") renderBauwerk(data);
      else if (view === "einzel") renderEinzel();
      else if (view === "live") renderLive();
      else if (view === "vergleich") renderVergleich();
      else if (view === "messung") renderMessung();
    },
  };
})();
