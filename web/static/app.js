"use strict";
/* € effect of one cited item: quantity × a unit price typed by the user.
   Pure: reads no page, stores nothing, sends nothing. Whole-number arithmetic
   (BigInt), so the cents are exact; the result is rounded half up to the cent.
   The price is read in the German form "1.250,50"; a dot is a thousands mark
   when groups of three digits follow it ("1.250" is 1250), else a decimal
   point ("12.5"); a space only as a thousands mark ("1 250,50"). Anything
   else inside the number ("12€50", "12 50") is no price.
   Returns { state: "empty" } for an empty field,
           { state: "error", message } for an input that is not a price,
           { state: "ok", quantity, price, effect, text } with German number texts.
   Twin for the tests: euro_effect in web/tests/test_web_eur_effect.py. */
function euroEffect(quantity, unit, priceText) {
  const group = (digits) => digits.replace(/\B(?=(\d{3})+$)/g, ".");
  let text = String(priceText === null || priceText === undefined ? "" : priceText).trim()
    .replace(/^(€|EUR)\s*/, "").replace(/\s*(€|EUR)$/, "");               // one sign before or after
  if (text === "") return { state: "empty" };
  if (/^\d{1,3}(\s\d{3})+(,\d+)?$/.test(text)) text = text.replace(/\s/g, "");  // "1 250,50"
  let whole, fraction = "";
  if (text.includes(",")) {
    const cut = text.lastIndexOf(",");
    whole = text.slice(0, cut);
    fraction = text.slice(cut + 1);
    if (!/^(\d{1,3}(\.\d{3})+|\d+)$/.test(whole) || !/^\d+$/.test(fraction)) whole = null;
  } else if (/^\d{1,3}(\.\d{3})+$/.test(text)) {
    whole = text;
  } else if (/^\d+(\.\d+)?$/.test(text)) {
    [whole, fraction = ""] = text.split(".");
  } else {
    whole = null;
  }
  if (whole === null) {
    return { state: "error", message: "Das ist kein Preis. Beispiel: 1.250,50 (Komma vor den Cent, Punkt nur als Tausenderzeichen)." };
  }
  whole = whole.replace(/\./g, "").replace(/^0+(?=\d)/, "");
  if (fraction.length > 4 || whole.length > 9) {
    return { state: "error", message: "Der Preis hat zu viele Stellen (höchstens 9 vor und 4 nach dem Komma)." };
  }
  if (typeof quantity !== "number" || !Number.isFinite(quantity) || quantity < 0 || quantity > 1e9) {
    return { state: "error", message: "Für diese Position steht keine Menge in der Liste; ohne Menge gibt es keinen €-Effekt." };
  }
  const price = BigInt(whole + fraction.padEnd(4, "0"));         // in 1/10 000 €
  const amount = BigInt(Math.round(quantity * 1e6));             // in 1/1 000 000 of the unit
  const cents = (price * amount + 50000000n) / 100000000n;       // half up
  const euros = (number) => group(String(number / 100n)) + "," + String(number % 100n).padStart(2, "0");
  const shownFraction = fraction.replace(/0+$/, "").padEnd(2, "0");
  const micro = String(amount).padStart(7, "0");
  const quantityFraction = micro.slice(-6).replace(/0+$/, "");
  const result = {
    state: "ok",
    quantity: group(micro.slice(0, -6)) + (quantityFraction ? "," + quantityFraction : ""),
    price: group(whole) + "," + shownFraction,
    effect: euros(cents),
  };
  result.text = result.quantity + (unit ? " " + unit : "") + " × " + result.price + " € = " + result.effect + " €";
  return result;
}
/* end of euroEffect */

/* LV-Prüfstand: views "Fund" and "Prüfen". No build step, no outside resource.
   All data comes from /api/findings; a review is written by POST /api/reviews/<id>.
   Text from the data files is put into the page as text only, never as HTML. */
(function () {
  const TYPE = { double_assignment: "Doppelt ausgeschrieben", contradiction: "Widerspruch", gap: "Lücke" };
  const SEVERITY = { high: "hoch", medium: "mittel", info: "Hinweis" };
  const SKEPTIC = { survived: "bestanden", weakened: "abgeschwächt" };
  const STATUS = { confirmed: "bestätigt", rejected: "verworfen", unclear: "unklar", open: "offen" };
  const KEYS = { b: "confirmed", v: "rejected", u: "unclear" };
  const BY_STORE = "lv-pruefstand-geprueft-von";
  const VIEWS = ["bauwerk", "fund", "pruefen", "einzel", "live", "vergleich", "messung"];

  const state = {
    data: null,
    loadError: null,
    view: VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "fund",
    filterOn: true,
    fundId: null,
    pruefId: null,
    drafts: {},
    unitPrices: {},  // typed unit prices: kept in this page only, never stored, never sent
    saving: Promise.resolve(),
  };

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

  function reviewStatus(finding) {
    const status = finding.review ? finding.review.status : null;
    return status === "confirmed" || status === "rejected" || status === "unclear" ? status : "open";
  }

  function formatEur(number) {
    return number.toLocaleString("de-DE", { maximumFractionDigits: 6 });
  }

  function findings() {
    return state.data ? state.data.findings : [];
  }

  function queue() {
    return state.filterOn ? findings().filter((finding) => finding.k3_pass) : findings();
  }

  function currentReviewFinding() {
    const list = queue();
    return list.find((finding) => finding.id === state.pruefId) || list[0] || null;
  }

  // ---- messages -----------------------------------------------------------

  function renderMessages() {
    const box = $("messages");
    box.replaceChildren();
    if (state.loadError) {
      box.append(el("p", { class: "message error", text: state.loadError }));
    }
    const data = state.data;
    if (!data) return;
    if (data.mode === "sample") {
      box.append(el("p", {
        class: "message", id: "sample-note",
        text: "Beispieldaten (synthetisch, keine echten Listen): " + data.missing +
          " wurde nicht gefunden. Gelesen wird " + data.source + ".",
      }));
    }
    if (!data.items_usable) {
      box.append(el("p", {
        class: "message",
        text: "items.json fehlt oder ist nicht lesbar: Gewerk und Kurztext der Positionen werden nicht gezeigt.",
      }));
    }
    if (data.contract_errors > 0) {
      box.append(el("p", {
        class: "message",
        text: data.contract_errors + " Stelle(n) in " + data.source + " passen nicht zum Vertrag v1. Beispiele: " +
          data.contract_error_examples.join(" | "),
      }));
    }
  }

  // ---- one finding --------------------------------------------------------

  function statusBadge(finding) {
    const status = reviewStatus(finding);
    return el("span", { class: "badge status-badge st-" + status, text: "Status: " + STATUS[status] });
  }

  /* The € field of one cited item. The typed price lives in state.unitPrices
     until the page is closed or loaded again; nothing here calls the server. */
  function euroBox(finding, source) {
    const key = finding.id + "/" + source.index;
    const box = el("div", { class: "euro" });
    const start = euroEffect(source.quantity, source.unit, "1");
    if (start.state !== "ok") {
      box.append(el("p", { class: "euro-none", text: "€-Effekt: Für diese Stelle steht keine Menge in der Liste." }));
      return box;
    }
    const input = el("input", { type: "text", inputmode: "decimal", class: "unit-price", autocomplete: "off",
      placeholder: "z. B. 1.250,50" });
    input.value = state.unitPrices[key] || "";
    const result = el("p", { class: "euro-result", "aria-live": "polite" });
    const show = () => {
      state.unitPrices[key] = input.value;
      const answer = euroEffect(source.quantity, source.unit, input.value);
      result.className = "euro-result" + (answer.state === "error" ? " error" : answer.state === "ok" ? " ok" : "");
      result.textContent = answer.state === "ok" ? "€-Effekt: " + answer.text
        : answer.state === "error" ? answer.message : "";
    };
    input.addEventListener("input", show);
    show();
    box.append(
      el("p", { class: "euro-quantity", text: "Menge laut Liste: " + start.quantity + (source.unit ? " " + source.unit : "") }),
      el("label", { class: "euro-field" }, "Einheitspreis in € (bleibt im Browser, wird nicht gespeichert)", input),
      result);
    return box;
  }

  function sourceBox(finding, source, withEuro) {
    const where = [source.doc || "Liste nicht angegeben"];
    if (source.trade) where.push(source.trade);
    const item = ["Position " + (source.item_no || "nicht angegeben"),
      source.page === null ? "Seite nicht angegeben" : "Seite " + source.page];
    const panel = el("div", { class: "page-panel", hidden: "" });
    const button = el("button", { type: "button", class: "show-source", text: "Quelle zeigen" });
    button.addEventListener("click", () => togglePage(finding, source, button, panel));
    return el("div", { class: "source" },
      el("div", { class: "where", text: where.join(" · ") }),
      el("div", { class: "item", text: item.join(" · ") }),
      source.short_text ? el("div", { class: "item", text: source.short_text }) : null,
      el("blockquote", { text: source.quote || "(kein Zitat)" }),
      button, panel, withEuro ? euroBox(finding, source) : null);
  }

  async function togglePage(finding, source, button, panel) {
    if (!panel.hidden) {
      panel.hidden = true;
      panel.replaceChildren();
      button.textContent = "Quelle zeigen";
      return;
    }
    panel.hidden = false;
    button.textContent = "Quelle ausblenden";
    panel.replaceChildren(el("p", { text: "Seitenbild wird geladen …" }));
    let message;
    try {
      const response = await fetch("/api/page-image/" + encodeURIComponent(finding.id) + "/" + source.index,
        { cache: "no-store" });
      if (response.ok) {
        const image = el("img", {
          src: URL.createObjectURL(await response.blob()),
          alt: "Seitenbild: " + (source.doc || "") + ", Seite " + (source.page === null ? "?" : source.page),
        });
        // The picture stays on the page after its address is given back.
        const release = () => URL.revokeObjectURL(image.src);
        image.addEventListener("load", release, { once: true });
        image.addEventListener("error", release, { once: true });
        panel.replaceChildren(image);
        return;
      }
      const body = await response.json().catch(() => ({}));
      if (response.status === 404 && body.expected) {
        message = "Für diese Quelle liegt kein Seitenbild vor (" + body.expected + " fehlt).";
      } else if (response.status === 404) {
        message = (body.error || "Das Seitenbild liegt nicht vor.");
      } else {
        message = "Das Seitenbild konnte nicht geladen werden. " + (body.error || "");
      }
    } catch (error) {
      message = "Das Seitenbild konnte nicht geladen werden (keine Verbindung zur Anwendung).";
    }
    panel.replaceChildren(el("p", { class: "no-image", text: message }));
  }

  function findingCard(finding, withReview) {
    const card = el("article", { class: "finding", "data-id": finding.id });
    card.append(el("div", { class: "head" },
      el("h2", { text: finding.id }),
      el("span", { class: "badge", text: "Art: " + label(TYPE, finding.type) }),
      el("span", { class: "badge sev-" + (finding.severity || ""), text: "Schwere: " + label(SEVERITY, finding.severity) }),
      statusBadge(finding)));

    const sources = el("div", { class: "sources" });
    for (const source of finding.sources) sources.append(sourceBox(finding, source, withReview));
    if (!finding.sources.length) sources.append(el("p", { text: "Dieser Fund nennt keine Quelle." }));
    card.append(sources);

    card.append(el("h3", { text: "Was ist unklar?" }),
      el("p", { class: "statement", text: finding.explanation_de || "nicht angegeben" }),
      el("h3", { text: "Frage an den Auftraggeber" }),
      el("p", { class: "statement", text: finding.question_de || "nicht angegeben" }),
      el("h3", { text: "Durchsuchte Listen (" + finding.lists_searched.length + ")" }),
      el("p", { text: finding.lists_searched.join(", ") || "keine angegeben" }),
      el("h3", { text: "Suchbegriffe" }),
      el("p", { text: finding.search_terms.join(", ") || "keine angegeben" }),
      el("h3", { text: "Gegenprüfung" }),
      el("p", { text: "Ergebnis: " + label(SKEPTIC, finding.skeptic.status) +
        (finding.skeptic.note ? " · Notiz: " + finding.skeptic.note : "") }),
      el("p", { text: "Zitate per Code geprüft: " + (finding.quotes_verified ? "ja" : "nein") }));

    if (!finding.k3_pass) {
      card.append(el("p", {
        class: "held-note",
        text: "Der Prüffilter hält diesen Fund zurück (Gegenprüfung nicht bestanden oder Zitate nicht geprüft).",
      }));
    }
    if (withReview) {
      card.append(el("p", { class: "euro-note", text: "€-Effekt = Menge × eingegebener Einheitspreis. Der Preis wird nicht " +
        "gespeichert; das Ergebnis kann in der Ansicht „Prüfen“ in „Schätzung in €“ eingetragen werden." }));
      card.append(reviewSummary(finding));
    }
    return card;
  }

  function reviewSummary(finding) {
    const box = el("div", { class: "review-summary" }, el("h3", { text: "Bewertung" }));
    const review = finding.review;
    if (reviewStatus(finding) === "open") {
      box.append(el("p", { text: "offen (noch nicht bewertet)" }));
      return box;
    }
    const parts = [STATUS[review.status]];
    if (review.by) parts.push("von " + review.by);
    if (review.at) parts.push("am " + review.at.replace("T", " um "));
    box.append(el("p", { text: parts.join(", ") }));
    if (review.comment) box.append(el("p", { text: "Kommentar: " + review.comment }));
    if (review.eur_estimate !== null) box.append(el("p", { text: "Schätzung: " + formatEur(review.eur_estimate) + " €" }));
    return box;
  }

  // ---- view "Fund" --------------------------------------------------------

  function renderFund() {
    const list = $("fund-list");
    const detail = $("fund-detail");
    const all = findings();
    const shown = all.find((finding) => finding.id === state.fundId) || all[0] || null;
    state.fundId = shown ? shown.id : null;
    list.replaceChildren();
    for (const finding of all) {
      const status = reviewStatus(finding);
      const button = el("button", { type: "button", class: finding === shown ? "active" : "", "data-id": finding.id },
        el("span", { class: "row" },
          el("strong", { text: finding.id }),
          el("span", { class: "badge st-" + status, text: STATUS[status] })),
        el("span", { class: "row" },
          el("span", { text: label(TYPE, finding.type) + " · " + label(SEVERITY, finding.severity) }),
          finding.k3_pass ? null : el("span", { class: "held", text: "zurückgehalten" })));
      button.addEventListener("click", () => { state.fundId = finding.id; renderFund(); });
      list.append(button);
    }
    detail.replaceChildren(shown ? findingCard(shown, true)
      : el("p", { class: "empty", text: state.data ? "Die Datei enthält keine Funde." : "" }));
  }

  // ---- view "Prüfen" ------------------------------------------------------

  function renderCounters() {
    const box = $("counters");
    box.replaceChildren();
    if (!state.data) return;
    const counters = state.data.counters;
    const numbers = state.filterOn ? counters.k3 : counters.all;
    const add = (name, number, text) => box.append(el("div", { class: "counter " + name, "data-counter": name },
      el("span", { class: "number", text: String(number) }), el("span", { class: "label", text: text })));
    add("confirmed", numbers.confirmed, "bestätigt");
    add("rejected", numbers.rejected, "verworfen");
    add("unclear", numbers.unclear, "unklar");
    add("open", numbers.open, "offen");
    add("count", numbers.count, "in der Liste");
    add("held", counters.held_back, state.filterOn ? "vom Prüffilter zurückgehalten" : "hielte der Prüffilter zurück (Filter aus)");
    const note = [];
    note.push(state.filterOn
      ? "Filter an: " + counters.k3.count + " von " + counters.all.count + " Funden in der Liste."
      : "Filter aus: alle " + counters.all.count + " Funde in der Liste.");
    if (counters.reviews_without_finding > 0) {
      note.push(counters.reviews_without_finding + " gespeicherte Bewertung(en) gehören zu Funden, die im aktuellen Lauf " +
        "nicht stehen; sie bleiben in reviews/" + state.data.project + ".json erhalten.");
    }
    $("k3-note").textContent = note.join(" ");
  }

  function setSaveNote(text, kind) {
    const note = $("save-note");
    note.textContent = text;
    note.className = "save-note" + (kind ? " " + kind : "");
  }

  function savedText(finding) {
    const review = finding.review;
    const parts = ["Gespeichert: " + STATUS[review.status]];
    if (review.at) parts.push(review.at.replace("T", " um "));
    if (review.by) parts.push(review.by);
    return parts.join(", ");
  }

  function markStatusButtons(finding) {
    const status = finding ? reviewStatus(finding) : "open";
    for (const button of document.querySelectorAll(".status-button")) {
      const active = button.dataset.status === status;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.disabled = !finding;
    }
  }

  function renderPruefen() {
    renderCounters();
    const list = queue();
    const finding = currentReviewFinding();
    state.pruefId = finding ? finding.id : null;
    const index = finding ? list.indexOf(finding) : -1;
    $("position").textContent = finding ? "Fund " + (index + 1) + " von " + list.length : "Fund 0 von 0";
    $("prev").disabled = index <= 0;
    $("next").disabled = index < 0 || index >= list.length - 1;
    $("pruefen-detail").replaceChildren(finding ? findingCard(finding, false)
      : el("p", { class: "empty", text: state.data ? "Kein Fund in der Liste." : "" }));
    const draft = finding ? state.drafts[finding.id] : null;
    const review = finding && reviewStatus(finding) !== "open" ? finding.review : null;
    $("comment").value = draft ? draft.comment : review ? review.comment : "";
    $("eur").value = draft ? draft.eur : review && review.eur_estimate !== null ? formatEur(review.eur_estimate) : "";
    $("comment").disabled = $("eur").disabled = !finding;
    markStatusButtons(finding);
    setSaveNote(review ? savedText(finding) : "", review ? "ok" : "");
  }

  function move(step) {
    const list = queue();
    const index = list.indexOf(currentReviewFinding());
    const target = list[index + step];
    if (!target) return;
    state.pruefId = target.id;
    renderPruefen();
    showFindingTop();
  }

  /* The finding scrolls in its own box between the counters and the review form
     (style.css, view "Prüfen"). After ← or → the new finding starts at the top of
     that box; the filter switch and the export buttons stand above it. */
  function showFindingTop() {
    const box = $("pruefen-scroll");
    if (box.scrollHeight > box.clientHeight + 1) box.scrollTop = $("pruefen-detail").offsetTop;
  }

  /* Keys that scroll a page scroll the box of the finding, wherever the focus is. */
  function scrollFinding(event) {
    const box = $("pruefen-scroll");
    if (box.scrollHeight <= box.clientHeight + 1) return false;  // low window: the page itself scrolls
    const page = Math.max(box.clientHeight - 60, 60);
    const steps = { ArrowDown: 60, ArrowUp: -60, PageDown: page, PageUp: -page, Home: -box.scrollHeight, End: box.scrollHeight };
    let step = steps[event.key];
    if (event.key === " " && event.target === document.body) step = event.shiftKey ? -page : page;
    if (step === undefined) return false;
    box.scrollTop += step;
    return true;
  }

  // ---- export (W8) --------------------------------------------------------

  /* Download one export file. The server builds it at this moment from the
     current reviews; a review that is still on its way is waited for. The
     request names the project the page shows; when the server reads another
     one by now, it sends no file and asks for a reload (as for a review). */
  async function exportFile(button) {
    const note = button.parentElement.querySelector(".export-note");
    const say = (text, kind) => { note.textContent = text; note.className = "export-note" + (kind ? " " + kind : ""); };
    button.disabled = true;
    say("Datei wird erstellt …", "");
    try {
      await state.saving;
      const shown = state.data ? "?project=" + encodeURIComponent(state.data.project) : "";
      const response = await fetch(button.dataset.export + shown, { cache: "no-store" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error || "Fehler " + response.status);
      }
      const blob = await response.blob();
      const named = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "");
      const name = named ? named[1] : button.dataset.name;
      const link = el("a", { href: URL.createObjectURL(blob), download: name, hidden: "" });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 60000);
      say("Exportiert: " + name + (/\.html$/.test(name)
        ? " (auf diesem Rechner druckt kein Chrome das PDF; die Datei im Browser öffnen und als PDF drucken)" : ""), "ok");
    } catch (error) {
      say("Export fehlgeschlagen: " + (error.message || "keine Verbindung zur Anwendung"), "error");
    } finally {
      button.disabled = false;
    }
  }

  /* Write one review. The form values are read now; the request waits for the
     one before it, so two quick actions reach the file in their order. After
     the answer only the counters, badges and buttons change; the form fields
     stay as they are, so a click in progress is never lost. */
  function save(finding, status) {
    const body = {
      status: status, comment: $("comment").value, eur_estimate: $("eur").value, by: $("by").value,
      project: state.data.project,
    };
    state.saving = state.saving.then(async () => {
      let answer = null;
      let problem = null;
      try {
        const response = await fetch("/api/reviews/" + encodeURIComponent(finding.id), {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        answer = await response.json().catch(() => ({}));
        if (!response.ok) problem = answer.error || "Fehler " + response.status;
      } catch (error) {
        problem = "keine Verbindung zur Anwendung";
      }
      const shown = state.pruefId === finding.id;
      if (problem) {
        if (shown) setSaveNote("NICHT gespeichert: " + problem, "error");
        return;
      }
      // The list may have been loaded again while the request ran.
      finding = findings().find((entry) => entry.id === finding.id) || finding;
      finding.review = answer.review;
      state.data.counters = answer.counters;
      delete state.drafts[finding.id];
      renderCounters();
      renderFund();
      if (shown) {
        const badge = document.querySelector("#pruefen-detail .status-badge");
        if (badge) badge.replaceWith(statusBadge(finding));
        markStatusButtons(finding);
        setSaveNote(savedText(finding), "ok");
      }
    });
    return state.saving;
  }

  function setStatus(status) {
    const finding = currentReviewFinding();
    if (finding) save(finding, status);
  }

  function fieldChanged() {
    const finding = currentReviewFinding();
    if (!finding) return;
    if (reviewStatus(finding) !== "open") {
      save(finding, finding.review.status);
    } else {
      setSaveNote("Noch nicht gespeichert: Kommentar und Schätzung werden mit der Bewertung (B, V oder U) gespeichert.", "");
    }
  }

  function fieldTyped() {
    const finding = currentReviewFinding();
    if (finding) state.drafts[finding.id] = { comment: $("comment").value, eur: $("eur").value };
  }

  // ---- page ---------------------------------------------------------------

  function render() {
    $("project").textContent = state.data ? state.data.project : "…";
    renderMessages();
    document.body.classList.toggle("in-pruefen", state.view === "pruefen");
    for (const name of VIEWS) {
      $("view-" + name).hidden = state.view !== name;
      $("tab-" + name).classList.toggle("active", state.view === name);
      $("tab-" + name).setAttribute("aria-pressed", state.view === name ? "true" : "false");
    }
    renderFund();
    renderPruefen();
    if (window.LVViews && window.LVViews.names.includes(state.view)) window.LVViews.render(state.view, state.data);
  }

  async function load() {
    try {
      const response = await fetch("/api/findings", { cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || "Fehler " + response.status);
      state.data = body;
      state.loadError = null;
    } catch (error) {
      state.loadError = "Die Funde konnten nicht geladen werden: " + error.message;
    }
    render();
  }

  function showView(name) {
    state.view = name;
    history.replaceState(null, "", "#" + name);
    load();
  }

  /* Used by the view "Bauwerk": a click on a finding of a cell opens it in the view "Fund". */
  window.LV = {
    openFinding(id) { state.fundId = id; showView("fund"); },
  };

  function start() {
    try { $("by").value = localStorage.getItem(BY_STORE) || ""; } catch (error) { /* no storage */ }
    $("by").addEventListener("change", () => {
      try { localStorage.setItem(BY_STORE, $("by").value); } catch (error) { /* no storage */ }
    });
    for (const tab of document.querySelectorAll(".tab")) {
      tab.addEventListener("click", () => showView(tab.dataset.view));
    }
    $("k3-switch").checked = true;
    $("k3-switch").addEventListener("change", () => {
      state.filterOn = $("k3-switch").checked;
      renderPruefen();
    });
    for (const button of document.querySelectorAll(".export-button")) {
      button.addEventListener("click", () => exportFile(button));
    }
    $("prev").addEventListener("click", () => move(-1));
    $("next").addEventListener("click", () => move(1));
    for (const button of document.querySelectorAll(".status-button")) {
      button.addEventListener("click", () => setStatus(button.dataset.status));
    }
    for (const id of ["comment", "eur"]) {
      $(id).addEventListener("input", fieldTyped);
      $(id).addEventListener("change", fieldChanged);
    }
    $("review-form").addEventListener("submit", (event) => event.preventDefault());
    window.addEventListener("hashchange", () => {
      const view = location.hash.slice(1);
      if (VIEWS.includes(view) && view !== state.view) showView(view);
    });
    document.addEventListener("keydown", (event) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const tag = event.target.tagName;
      if (tag === "INPUT" && event.target.type !== "checkbox") {
        if (event.key === "Enter" || event.key === "Escape") {
          event.preventDefault();
          event.target.blur();
        }
        return;
      }
      if (state.view !== "pruefen") return;
      const status = KEYS[(event.key || "").toLowerCase()];
      if (status) { event.preventDefault(); setStatus(status); }
      else if (event.key === "ArrowRight") { event.preventDefault(); move(1); }
      else if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); }
      else if (scrollFinding(event)) event.preventDefault();
    });
    load();
  }

  start();
})();
