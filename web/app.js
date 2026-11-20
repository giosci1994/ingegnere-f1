// Ingegnere F1 · la pagina del cellulare.
// Radio: un solo elemento <audio>, sbloccato dal tocco su «Collega la radio» (iPhone),
// le frasi in fila una dopo l'altra; una frase urgente può tagliarne una meno importante.
// Schermo acceso: Wake Lock se c'è (vuole HTTPS), altrimenti un video nero muto in loop.
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let ws = null, wsAttesa = 1000, collegato = false;
let coda = [], inOnda = null, impostazioni = null, wakeLock = null;
const audio = $("#radio");
const sveglia = $("#sveglia");

// ---------- viste ----------
$$("nav button").forEach((b) => b.addEventListener("click", () => {
  $$("nav button").forEach((x) => x.classList.toggle("attivo", x === b));
  $$(".vista").forEach((v) => v.classList.toggle("attiva", v.id === "v-" + b.dataset.vista));
  if (b.dataset.vista === "gare") caricaGare();
  if (b.dataset.vista === "info") caricaRegistrazioni();
  if (b.dataset.vista === "traiettoria") caricaPiste();
}));

// ---------- WebSocket ----------
function apri() {
  const prot = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${prot}://${location.host}/ws`);
  ws.onopen = () => { wsAttesa = 1000; };
  ws.onmessage = (e) => {
    let d; try { d = JSON.parse(e.data); } catch { return; }
    if (d.tipo === "stato") mostraStato(d);
    else if (d.tipo === "radio") arriva(d);
  };
  ws.onclose = () => {
    $("#ps5").textContent = "Server: riconnessione…";
    $("#ps5").className = "ps5 spento";
    setTimeout(apri, wsAttesa);
    wsAttesa = Math.min(wsAttesa * 2, 10000);
  };
}

// ---------- radio ----------
function silenzio() {
  // 0,1 s di silenzio in WAV, per sbloccare l'audio con il tocco
  const sr = 8000, n = 800, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true);
  v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
  return URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
}

async function collega() {
  try { if (navigator.audioSession) navigator.audioSession.type = "playback"; } catch {}
  try {
    audio.src = silenzio();
    await audio.play();
    collegato = true;
  } catch (e) {
    $("#nota-radio").textContent = "L'audio non è partito: tocca di nuovo «Collega la radio».";
    $("#nota-radio").classList.add("avviso");
    return;
  }
  await schermoAcceso();
  const b = $("#collega");
  b.textContent = "📻 Radio collegata";
  b.classList.add("collegato");
  $("#nota-radio").textContent = "Lascia la pagina aperta, con lo schermo acceso. Se cambi app, torna qui e tocca di nuovo.";
  $("#nota-radio").classList.remove("avviso");
  suonaProssima();
}

async function schermoAcceso() {
  if ("wakeLock" in navigator) {
    try { wakeLock = await navigator.wakeLock.request("screen"); return; } catch {}
  }
  try { await sveglia.play(); } catch {}
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && collegato) {
    schermoAcceso();
    if (audio.paused && inOnda) { inOnda = null; suonaProssima(); }
  }
});

function arriva(d) {
  aggiungiFrase(d);
  if (!collegato) return;
  if (d.interrompi && inOnda && inOnda.priorita >= 3) {
    audio.pause();
    inOnda = null;
    coda = coda.filter((x) => x.priorita < 3);
    coda.unshift(d);
  } else {
    coda.push(d);
  }
  suonaProssima();
}

function suonaProssima() {
  if (inOnda || !coda.length || !collegato) return;
  coda.sort((a, b) => a.priorita - b.priorita);
  const d = coda.shift();
  inOnda = d;
  audio.src = d.url;
  audio.play().catch(() => {
    inOnda = null;
    $("#nota-radio").textContent = "L'audio si è fermato: tocca «Collega la radio».";
    $("#nota-radio").classList.add("avviso");
    $("#collega").classList.remove("collegato");
    $("#collega").textContent = "📻 Collega la radio";
    collegato = false;
  });
}
audio.addEventListener("ended", () => { inOnda = null; setTimeout(suonaProssima, 250); });
audio.addEventListener("error", () => { if (inOnda) { inOnda = null; suonaProssima(); } });
$("#collega").addEventListener("click", collega);

function aggiungiFrase(d) {
  const ul = $("#frasi");
  ul.querySelector(".vuoto")?.remove();
  const li = document.createElement("li");
  li.className = "p" + d.priorita;
  li.innerHTML = `<small></small><span></span>`;
  li.querySelector("small").textContent = `${d.ora || ""} · ${d.categoria}`;
  li.querySelector("span").textContent = d.testo;
  ul.prepend(li);
  while (ul.children.length > 12) ul.lastChild.remove();
}

// ---------- stato ----------
const fmt = (x, suff = "") => (x === null || x === undefined ? "–" : x + suff);
function mostraStato(s) {
  const p = $("#ps5");
  if (s.connesso) {
    p.textContent = `PS5 collegata · ${s.sessione || ""}${s.pista ? " · " + s.pista : ""}${s.in_pausa ? " · in pausa" : ""}${s.silenzio ? " · silenzio radio" : ""}`;
    p.className = "ps5 acceso";
  } else {
    p.textContent = s.ricevuti ? "PS5: nessun dato da qualche secondo" : "PS5: in attesa dei dati…";
    p.className = "ps5 spento";
  }
  const a = s.auto || {};
  $("#c-pos").textContent = a.posizione ? "P" + a.posizione : "–";
  $("#c-giro").textContent = a.giro ? (a.giri_totali ? `${a.giro}/${a.giri_totali}` : a.giro) : "–";
  $("#c-davanti").textContent = a.davanti != null ? "+" + a.davanti.toFixed(1) : "–";
  $("#c-dietro").textContent = a.dietro != null ? "−" + a.dietro.toFixed(1) : "–";
  $("#c-gomme").textContent = a.gomma ? `${a.gomma}${a.eta_gomme != null ? " " + a.eta_gomme : ""}` : "–";
  $("#c-usura").textContent = fmt(a.usura, "%");
  $("#c-benzina").textContent = a.carburante != null ? (a.carburante > 0 ? "+" : "") + a.carburante : "–";
  $("#c-batteria").textContent = fmt(a.batteria, "%");
  if (!$("#frasi li:not(.vuoto)") && s.frasi && s.frasi.length) {
    s.frasi.forEach((f) => aggiungiFrase(f));
  }
  const tk = s.tasti || {};
  $("#t-azione").textContent = tk.azione ? `${tk.azione.nome} alle ${tk.azione.ora}${tk.azione.domanda ? " → " + ((impostazioni && impostazioni.domande[tk.azione.domanda]) || tk.azione.domanda) : " (nessuna domanda assegnata)"}` : "nessuna";
  $("#t-tasto").textContent = tk.tasto ? `${tk.tasto.nome} alle ${tk.tasto.ora}` : "nessuno";
  const dl = $("#diagnosi");
  const righe = [
    ["PS5", s.connesso ? `collegata (${s.mittente})` : "non collegata"],
    ["Formato UDP", s.formato || "–"],
    ["Versione del gioco", s.versione_gioco || "–"],
    ["Pacchetti al secondo", s.pacchetti_al_secondo],
    ["Pacchetti ricevuti", s.ricevuti],
    ["Pacchetti scartati", s.scartati + (s.taglie_scartate.length ? " (" + s.taglie_scartate.join(", ") + ")" : "")],
    ["Telefoni collegati", s.clienti],
    ["Frasi pronte", s.cache_pronta + "%"],
    ["Registrazione", s.registrazione || "–"],
  ];
  dl.innerHTML = "";
  righe.forEach(([k, v]) => {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v;
    dl.append(dt, dd);
  });
}

// ---------- impostazioni ----------
async function caricaImpostazioni() {
  const r = await fetch("/api/impostazioni");
  impostazioni = await r.json();
  disegnaImpostazioni();
}

function disegnaImpostazioni() {
  const v = impostazioni.valori;
  const box = $("#categorie");
  box.innerHTML = "";
  impostazioni.categorie.forEach((c) => {
    const l = document.createElement("label");
    l.className = "interruttore";
    l.innerHTML = `<input type="checkbox"><span></span>`;
    l.querySelector("span").textContent = c.etichetta;
    const i = l.querySelector("input");
    i.checked = v.avvisi[c.id] !== false;
    i.addEventListener("change", () => salva({ avvisi: { [c.id]: i.checked } }));
    box.append(l);
  });
  $$("#verbosita button").forEach((b) => b.classList.toggle("attivo", +b.dataset.v === v.verbosita));
  $$("#voce button").forEach((b) => b.classList.toggle("attivo", b.dataset.voce === v.voce));
  $("#volume").value = v.volume; $("#o-volume").textContent = v.volume + "%";
  $("#velocita").value = v.velocita; $("#o-velocita").textContent = (+v.velocita).toFixed(2) + "×";
  $("#effetto").value = v.effetto_radio;
  $("#o-effetto").textContent = ["niente", "leggero", "normale", "forte"][v.effetto_radio];
  $("#registra").checked = v.registra;
  $("#salva_giri").checked = v.salva_giri;
  $("#assetto").checked = v.assetto;
  $("#silenzio_qualifica").checked = v.silenzio_qualifica;
  $("#una_curva_alla_volta").checked = v.una_curva_alla_volta;
  disegnaTasti(v.tasti || {});
  if (document.activeElement !== $("#pilota")) $("#pilota").value = v.pilota;
}

let salvaTimer = null;
async function salva(nuovi) {
  const r = await fetch("/api/impostazioni", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(nuovi) });
  impostazioni = await r.json();
  disegnaImpostazioni();
  $("#salvato").textContent = "Salvato sul server.";
  clearTimeout(salvaTimer);
  salvaTimer = setTimeout(() => ($("#salvato").textContent = ""), 2000);
}

$$("#verbosita button").forEach((b) => b.addEventListener("click", () => salva({ verbosita: +b.dataset.v })));
$$("#voce button").forEach((b) => b.addEventListener("click", () => salva({ voce: b.dataset.voce })));
$("#volume").addEventListener("input", (e) => ($("#o-volume").textContent = e.target.value + "%"));
$("#volume").addEventListener("change", (e) => salva({ volume: +e.target.value }));
$("#velocita").addEventListener("input", (e) => ($("#o-velocita").textContent = (+e.target.value).toFixed(2) + "×"));
$("#velocita").addEventListener("change", (e) => salva({ velocita: +e.target.value }));
$("#effetto").addEventListener("change", (e) => salva({ effetto_radio: +e.target.value }));
$("#registra").addEventListener("change", (e) => salva({ registra: e.target.checked }));
$("#salva_giri").addEventListener("change", (e) => salva({ salva_giri: e.target.checked }));
$("#assetto").addEventListener("change", (e) => salva({ assetto: e.target.checked }));
$("#pilota").addEventListener("change", (e) => salva({ pilota: e.target.value }));
$("#silenzio_qualifica").addEventListener("change", (e) => salva({ silenzio_qualifica: e.target.checked }));
$("#una_curva_alla_volta").addEventListener("change", (e) => salva({ una_curva_alla_volta: e.target.checked }));

// ---------- domande dai tasti (UDP Action 1–12) ----------
function disegnaTasti(tasti) {
  const box = $("#tasti");
  if (box.contains(document.activeElement)) return;
  box.innerHTML = "";
  const domande = impostazioni.domande || {};
  for (let n = 1; n <= 12; n++) {
    const l = document.createElement("label"); l.textContent = "UDP Action " + n; l.htmlFor = "tasto-" + n;
    const sel = document.createElement("select"); sel.className = "campo"; sel.id = "tasto-" + n;
    const vuota = document.createElement("option"); vuota.value = ""; vuota.textContent = "— niente —"; sel.append(vuota);
    Object.entries(domande).forEach(([k, et]) => { const o = document.createElement("option"); o.value = k; o.textContent = et; sel.append(o); });
    sel.value = tasti[String(n)] || "";
    sel.addEventListener("change", () => salva({ tasti: { [String(n)]: sel.value } }));
    box.append(l, sel);
  }
}

// ---------- pronuncia ----------
async function suonaProva(corpo, bottone) {
  if (!collegato) await collega();
  const testo = bottone.textContent;
  bottone.disabled = true; bottone.textContent = "…";
  try {
    const r = await fetch("/api/prova", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    const d = await r.json();
    arriva({ ...d, priorita: 0, categoria: "prova", ora: new Date().toLocaleTimeString("it-IT") });
  } finally { bottone.disabled = false; bottone.textContent = testo; }
}
async function chiamaPronuncia(corpo) {
  const r = await fetch("/api/pronuncia", corpo ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) } : undefined);
  if (!r.ok) { $("#salvato").textContent = "Non salvato: " + (await r.text()); return; }
  disegnaPronuncia((await r.json()).voci);
  if (corpo) { $("#salvato").textContent = "Salvato sul server."; clearTimeout(salvaTimer); salvaTimer = setTimeout(() => ($("#salvato").textContent = ""), 2000); }
}
function disegnaPronuncia(voci) {
  const ul = $("#pronuncia");
  ul.innerHTML = "";
  voci.forEach((v) => {
    const li = document.createElement("li");
    if (v.origine === "tolta") li.className = "tolta";
    const p = document.createElement("span"); p.textContent = v.parola;
    const g = document.createElement("input"); g.type = "text"; g.maxLength = 40; g.value = v.grafia; g.setAttribute("aria-label", "Come si dice " + v.parola);
    const az = document.createElement("div"); az.className = "azioni";
    const b = (t, f, titolo) => { const x = document.createElement("button"); x.textContent = t; x.title = titolo; x.addEventListener("click", () => f(x)); az.append(x); return x; };
    b("▶︎", (x) => suonaProva({ grafia: g.value }, x), "Prova");
    if (v.origine === "tolta") {
      g.disabled = true;
      b("↺", () => chiamaPronuncia({ parola: v.parola, rimetti: true }), "Rimetti");
    } else {
      b("✓", () => chiamaPronuncia({ parola: v.parola, grafia: g.value }), "Salva");
      b(v.origine === "cambiata" ? "↺" : "✕", () => chiamaPronuncia({ parola: v.parola, togli: true }),
        v.origine === "cambiata" ? "Torna a quella di partenza" : "Togli");
    }
    const nota = document.createElement("small");
    nota.textContent = { partenza: "di partenza", mia: "tua", cambiata: `cambiata (di partenza: ${v.partenza})`, tolta: "tolta" }[v.origine] || "";
    li.append(p, g, az, nota);
    ul.append(li);
  });
}
$("#p-prova").addEventListener("click", (e) => suonaProva({ grafia: $("#p-grafia").value || $("#p-parola").value }, e.target));
$("#p-salva").addEventListener("click", async () => {
  await chiamaPronuncia({ parola: $("#p-parola").value, grafia: $("#p-grafia").value });
  $("#p-parola").value = ""; $("#p-grafia").value = "";
});

$("#prova-voce").addEventListener("click", async () => {
  if (!collegato) await collega();
  const b = $("#prova-voce");
  b.disabled = true; b.textContent = "…";
  try {
    const r = await fetch("/api/prova", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ testo: $("#testo-prova").value }) });
    const d = await r.json();
    arriva({ ...d, priorita: 0, categoria: "prova", ora: new Date().toLocaleTimeString("it-IT") });
  } finally { b.disabled = false; b.textContent = "▶︎ Prova la voce"; }
});


// ---------- dopo la gara ----------
async function caricaGare() {
  const r = await fetch("/api/riassunti");
  const el = await r.json();
  const ul = $("#elenco-gare");
  ul.innerHTML = el.length ? "" : `<li class="nota">Ancora nessun riassunto: arriva da solo alla fine di una sessione.</li>`;
  el.forEach((g) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.textContent = `${g.creato} · ${g.sessione}${g.pista ? " a " + g.pista : ""} · ${g.posizione ? "P" + g.posizione : ""}`;
    b.addEventListener("click", () => mostraGara(g.id));
    li.append(b); ul.append(li);
  });
}

const t = (x) => (x == null ? "–" : String(x));
function td(testo, cls) { const c = document.createElement("td"); c.textContent = t(testo); if (cls) c.className = cls; return c; }

async function mostraGara(id) {
  const r = await (await fetch("/api/riassunti/" + encodeURIComponent(id))).json();
  const box = $("#dettaglio-gara");
  box.innerHTML = "";
  const s = document.createElement("div");
  s.className = "scheda";
  const h = document.createElement("h3");
  h.textContent = `${r.sessione}${r.pista ? " a " + r.pista : ""}${r.chi_guida ? " · guida " + r.chi_guida : ""}`;
  s.append(h);
  const num = document.createElement("div");
  num.className = "numeri";
  const f = r.finale || {};
  [["Posizione", r.posizione ? "P" + r.posizione : "–"], ["Partenza", r.griglia ? "P" + r.griglia : "–"],
   ["Giro migliore", r.migliore ? `${r.migliore.tempo}` : "–"],
   ["Passo medio", r.passo ? r.passo.media : "–"], ["Costanza", r.passo ? "±" + r.passo.costanza_s + " s" : "–"],
   ["Soste", f.soste ?? (r.soste ? r.soste.length : "–")]]
    .forEach(([k, v]) => { const d = document.createElement("div"); d.innerHTML = "<b></b><span></span>"; d.querySelector("b").textContent = v; d.querySelector("span").textContent = k; num.append(d); });
  s.append(num);

  const righe = [];
  if (r.settori_migliori && r.settori_migliori.length)
    righe.push("Settori migliori: " + r.settori_migliori.map((x) => x.settore === "ideale" ? `giro ideale ${x.tempo}` : `S${x.settore} ${x.tempo} (giro ${x.giro})`).join(" · "));
  if (f.stint && f.stint.length) righe.push("Gomme: " + f.stint.map((x) => `${x.gomma} ${x.fino_al_giro ? "fino al giro " + x.fino_al_giro : "fino alla fine"}`).join(" → "));
  if (r.soste && r.soste.length) righe.push("Soste: " + r.soste.map((x) => `giro ${x.giro}${x.secondi_in_pit_lane ? ", " + x.secondi_in_pit_lane + " s in pit lane" : ""}`).join(" · "));
  const e = r.errori || {};
  const err = [];
  if (e.giri_non_validi && e.giri_non_validi.length) err.push(`giri non validi: ${e.giri_non_validi.join(", ")}`);
  if (e.avvertimenti_limiti) err.push(`avvertimenti limiti: ${e.avvertimenti_limiti}`);
  if (e.penalita && e.penalita.length) {
    // le stesse penalità una volta sola, con quante volte («avvertimento ×8»)
    const conta = new Map();
    e.penalita.forEach((p) => { const k = p.nome + (p.secondi ? ` ${p.secondi} s` : ""); conta.set(k, (conta.get(k) || 0) + 1); });
    err.push("penalità: " + Array.from(conta, ([k, n]) => (n > 1 ? `${k} ×${n}` : k)).join(", "));
  }
  if (e.contatti) err.push(`contatti: ${e.contatti}`);
  if (e.flashback) err.push(`flashback: ${e.flashback}`);
  righe.push("Errori: " + (err.length ? err.join(" · ") : "nessuno"));
  righe.forEach((x) => { const p = document.createElement("p"); p.textContent = x; s.append(p); });

  const tab = document.createElement("div");
  tab.className = "tabella";
  const table = document.createElement("table");
  table.innerHTML = "<thead><tr><th>Giro</th><th>Tempo</th><th>S1</th><th>S2</th><th>S3</th><th>Pos</th><th>Gomma</th><th></th></tr></thead><tbody></tbody>";
  const tb = table.querySelector("tbody");
  (r.giri || []).forEach((g) => {
    const tr = document.createElement("tr");
    if (r.migliore && g.giro === r.migliore.giro) tr.className = "migliore";
    tr.append(td(g.giro), td(g.tempo, g.valido ? "" : "no"), td(g.s1), td(g.s2), td(g.s3),
      td(g.posizione ? "P" + g.posizione : null), td(g.gomma), td([g.box ? "box" : "", g.safety_car ? "SC" : ""].filter(Boolean).join(" ")));
    tb.append(tr);
  });
  tab.append(table); s.append(tab);
  box.append(s);
  sezioniFase2(r, box);
  s.scrollIntoView({ behavior: "smooth" });
}
$("#crea-riassunto").addEventListener("click", async () => {
  await fetch("/api/riassunti/crea", { method: "POST" });
  caricaGare();
});

async function caricaRegistrazioni() {
  const el = await (await fetch("/api/registrazioni")).json();
  const ul = $("#registrazioni");
  ul.innerHTML = el.length ? "" : `<li>Nessuna registrazione.</li>`;
  el.slice(0, 10).forEach((x) => { const li = document.createElement("li"); li.textContent = `${x.nome} · ${x.mb} MB${x.in_corso ? " · in corso" : ""}`; ul.append(li); });
}

// ---------- riassunto: guida, assetto, strategia, ali ----------
function scheda(titolo, box) {
  const s = document.createElement("div"); s.className = "scheda";
  const h = document.createElement("h3"); h.textContent = titolo; s.append(h);
  box.append(s); return s;
}
function riga(s, testo) { const p = document.createElement("p"); p.textContent = testo; s.append(p); return p; }
function tabella(s, intest, righe) {
  const tab = document.createElement("div"); tab.className = "tabella";
  const tbl = document.createElement("table");
  const tr = document.createElement("tr");
  intest.forEach((x) => { const th = document.createElement("th"); th.textContent = x; tr.append(th); });
  const thead = document.createElement("thead"); thead.append(tr); tbl.append(thead);
  const tb = document.createElement("tbody");
  // le colonne con le frasi («Perché», «Come migliorare») vanno a capo invece di allargare la tabella
  righe.forEach((r) => { const q = document.createElement("tr"); r.forEach((x) => q.append(td(x, typeof x === "string" && x.length > 24 ? "testo" : ""))); tb.append(q); });
  tbl.append(tb); tab.append(tbl); s.append(tab);
}
const sec = (ms) => (ms == null ? "–" : (ms / 1000).toFixed(3));
const metri = (x) => (x == null ? "–" : String(Math.round(x)));
function sezioniFase2(r, box) {
  if (r.guida) {
    const s = scheda("Staccate e uscite", box);
    const rif = r.riferimento || {};
    riga(s, `Rispetto al giro migliore${rif.da_biblioteca ? " salvato" : ""}${rif.giro ? " (giro " + rif.giro + ", " + sec(rif.tempo_ms) + ")" : ""}.`);
    if (r.guida.dove_perdi.length)
      riga(s, "Dove perdi di più: " + r.guida.dove_perdi.map((c) => `${String(c.curva).includes(" e ") ? "curve" : "curva"} ${c.curva} (${c.perdita_media_s.toFixed(2)} s a giro${c.causa_frequente ? ", " + c.causa_frequente : ""})`).join(" · "));
    tabella(s, ["Curva", "Apice m", "Frenata m", "V min", "Gas m", "Perdi s", "Perché", "Come migliorare"],
      r.guida.curve.map((c) => [c.curva, c.apice_m, c.frenata_rif_m, c.vmin_rif, c.gas_rif_m,
        c.perdita_media_s == null ? null : c.perdita_media_s.toFixed(2), c.causa_frequente, c.consiglio]));
    if (r.guida.sistemate && r.guida.sistemate.length) riga(s, "Curve sistemate in prova: " + r.guida.sistemate.join(", ") + ".");
    riga(s, (r.guida.numerazione === "ufficiale"
      ? "Numeri delle curve: quelli ufficiali del circuito («1 e 2» = una chicane o una esse). "
      : "Numeri delle curve: la nostra numerazione, in ordine sul giro (per questa pista non c'è la tabella ufficiale). ") +
      "Frenata, velocità minima e gas sono quelli del giro migliore; «perdi» è la media sugli altri giri puliti.").className = "nota";
  }
  if (r.assetto) {
    const s = scheda("Assetto (consigli indicativi)", box);
    const a = r.assetto;
    if (a.consigli && a.consigli.length) a.consigli.forEach((c) => {
      const d = document.createElement("div"); d.className = "consiglio";
      d.innerHTML = "<span></span><small></small>";
      d.querySelector("span").textContent = c.consiglio;
      d.querySelector("small").textContent = "Perché: " + c.dato;
      s.append(d);
    });
    else riga(s, "Nessun consiglio: i dati non mostrano niente di netto.");
    if (a.assetto) {
      const voci = Object.entries(a.assetto).map(([k, v]) => [k.replaceAll("_", " "), Array.isArray(v) ? v.join(" / ") : v]);
      tabella(s, ["Assetto usato", "Valore"], voci);
    }
    if (a.nota) riga(s, a.nota).className = "nota";
  }
  if (r.strategia) {
    const s = scheda("Strategia", box);
    const st = r.strategia;
    riga(s, `Tempo perso al box: ${st.perdita_box_s} s (${st.misurata ? "misurato su questa pista" : "stima generica, ancora nessuna misura"}).`);
    if (st.degrado_s_per_giro != null) riga(s, `Le tue gomme perdevano circa ${st.degrado_s_per_giro.toFixed(2)} s a giro.`);
  }
  if (r.ali) {
    const s = scheda("Ali mobili 2026", box);
    riga(s, `Zone: ${t(r.ali.zone_complete)} complete, ${t(r.ali.zone_ridotte)} ridotte. Avvisi «ali in modalità rettilineo»: ${r.ali.avvisi}.`);
    tabella(s, ["Giro", "Metri disponibili", "Usate in rettilineo"], r.ali.giri.map((g) => [g.giro, g.metri_disponibili, g.uso_percento + "%"]));
  }
}

// ---------- traiettoria ----------
let giriPista = [], confrontoDati = null, zoomCurva = null;
async function caricaPiste() {
  const piste = await (await fetch("/api/piste")).json();
  const sel = $("#t-pista");
  const prima = sel.value;
  sel.innerHTML = "";
  if (!piste.length) {
    $("#t-mappa").innerHTML = '<p class="nota" style="padding:12px">Ancora nessun giro salvato: si salvano da soli mentre guidi.</p>';
    return;
  }
  piste.forEach((p) => { const o = document.createElement("option"); o.value = p.pista; o.textContent = `${p.nome} (${p.giri} giri)`; sel.append(o); });
  if (prima && piste.some((p) => String(p.pista) === prima)) sel.value = prima;
  await caricaGiri();
}
function nomeGiro(m) {
  return `${m.id.slice(6, 8)}/${m.id.slice(4, 6)} ${m.id.slice(9, 11)}:${m.id.slice(11, 13)} · ${m.pilota || ""} · giro ${m.giro} · ${sec(m.tempo_ms)}` +
    `${m.valido ? "" : " (non valido)"}${m.box ? " box" : ""}${m.safety_car ? " SC" : ""} · ${m.sessione}`;
}
async function caricaGiri() {
  giriPista = await (await fetch("/api/giri/" + $("#t-pista").value)).json();
  const a = $("#t-a"), b = $("#t-b");
  a.innerHTML = ""; b.innerHTML = "";
  giriPista.forEach((m) => {
    [a, b].forEach((s) => { const o = document.createElement("option"); o.value = m.id; o.textContent = nomeGiro(m); s.append(o); });
  });
  const validi = giriPista.filter((m) => m.valido && !m.box && !m.safety_car).sort((x, y) => x.tempo_ms - y.tempo_ms);
  const migliore = validi[0] || giriPista[0];
  if (giriPista.length) a.value = giriPista[0].id;
  if (migliore) b.value = migliore.id;
  await confronta();
}
async function confronta() {
  const p = $("#t-pista").value, a = $("#t-a").value, b = $("#t-b").value;
  if (!a || !b) return;
  const r = await fetch(`/api/confronto/${p}?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  if (!r.ok) return;
  confrontoDati = await r.json();
  zoomCurva = null;
  const cb = $("#t-curve"); cb.innerHTML = "";
  const tutto = document.createElement("button"); tutto.textContent = "Tutta la pista"; tutto.className = "attivo";
  tutto.addEventListener("click", () => { zoomCurva = null; disegna(); segna(tutto); });
  cb.append(tutto);
  confrontoDati.apici.forEach((c) => {
    const x = document.createElement("button"); x.textContent = (String(c.curva).includes(" e ") ? "Curve " : "Curva ") + c.curva;
    x.addEventListener("click", () => { zoomCurva = c; disegna(); segna(x); });
    cb.append(x);
  });
  disegna();
  const box = $("#t-tabella");
  box.innerHTML = "";
  tabella(box, ["Curva", "Delta s", "Frenata m", "V min", "Gas m", "Perché", "Come migliorare"],
    confrontoDati.curve.map((c) => [c.nome || c.curva, c.delta == null ? null : (c.delta > 0 ? "+" : "") + c.delta.toFixed(2),
      `${metri(c.giro.frenata)} / ${metri(c.riferimento.frenata)}`,
      `${t(c.giro.vmin)} / ${t(c.riferimento.vmin)}`,
      `${metri(c.giro.gas)} / ${metri(c.riferimento.gas)}`,
      c.frase, c.consiglio]));
  riga(box, "Nelle colonne: giro rosso / giro grigio. Delta positivo = il giro rosso è più lento in quella curva.").className = "nota";
}
function segna(btn) { $$("#t-curve button").forEach((b) => b.classList.toggle("attivo", b === btn)); }
function disegna() {
  const d = confrontoDati;
  if (!d) return;
  const tutti = d.a.linea.concat(d.b.linea);
  if (!tutti.length) { $("#t-mappa").innerHTML = '<p class="nota" style="padding:12px">Questi giri non hanno le posizioni.</p>'; return; }
  const xs = tutti.map((p) => p[0]), zs = tutti.map((p) => -p[1]);
  let minx = Math.min(...xs), maxx = Math.max(...xs), minz = Math.min(...zs), maxz = Math.max(...zs);
  if (zoomCurva) { const r = 180; minx = zoomCurva.x - r; maxx = zoomCurva.x + r; minz = -zoomCurva.z - r; maxz = -zoomCurva.z + r; }
  const lato = Math.max(maxx - minx, maxz - minz) * 1.08;
  const cx = (minx + maxx) / 2, cz = (minz + maxz) / 2;
  const linea = (l) => l.map((p) => `${p[0].toFixed(1)},${(-p[1]).toFixed(1)}`).join(" ");
  const fs = lato / 28;
  let svg = `<svg viewBox="${cx - lato / 2} ${cz - lato / 2} ${lato} ${lato}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Traiettoria">`;
  svg += `<polyline points="${linea(d.b.linea)}" fill="none" stroke="#9aa3b0" stroke-width="7" vector-effect="non-scaling-stroke" stroke-linejoin="round" opacity="0.8"/>`;
  svg += `<polyline points="${linea(d.a.linea)}" fill="none" stroke="#e10600" stroke-width="2.5" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>`;
  d.apici.forEach((c) => {
    if (c.x == null) return;
    // «13 e 14» sulla mappa diventa «13-14», in un'etichetta larga quanto il testo
    const et = String(c.curva).replace(" e ", "-");
    const w = fs * (0.62 * et.length + 0.6), h = fs * 1.25;
    svg += `<rect x="${c.x - w / 2}" y="${-c.z - h / 2}" width="${w}" height="${h}" rx="${h / 2}" fill="#0d0f12" stroke="#eef1f5" vector-effect="non-scaling-stroke"/>`;
    svg += `<text x="${c.x}" y="${-c.z + fs * 0.35}" font-size="${fs}" text-anchor="middle" fill="#eef1f5" font-family="system-ui">${et}</text>`;
  });
  svg += "</svg>";
  $("#t-mappa").innerHTML = svg;
}
$("#t-pista").addEventListener("change", caricaGiri);
$("#t-a").addEventListener("change", confronta);
$("#t-b").addEventListener("change", confronta);

// ---------- avvio ----------
if (/^\d+\.\d+\.\d+\.\d+$/.test(location.hostname)) $("#ip-server").textContent = location.hostname;
caricaImpostazioni();
chiamaPronuncia();
apri();
{ const b = document.querySelector(`nav button[data-vista="${location.hash.slice(1)}"]`); if (b) b.click(); }
