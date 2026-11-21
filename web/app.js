// Ingegnere F1 · la pagina del cellulare.
// Radio: un solo elemento <audio>, sbloccato dal tocco su «Collega la radio» (iPhone),
// le frasi in fila una dopo l'altra; una frase urgente può tagliarne una meno importante.
// Schermo acceso: Wake Lock se c'è (vuole HTTPS), altrimenti un video nero muto in loop.
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let ws = null, wsAttesa = 1000, collegato = false, ultimoPistaLive = null;
let coda = [], inOnda = null, impostazioni = null, wakeLock = null;
const audio = $("#radio");
const sveglia = $("#sveglia");

// ---------- viste ----------
$$("nav button").forEach((b) => b.addEventListener("click", () => {
  $$("nav button").forEach((x) => x.classList.toggle("attivo", x === b));
  $$(".vista").forEach((v) => v.classList.toggle("attiva", v.id === "v-" + b.dataset.vista));
  if (b.dataset.vista === "pregara") caricaPregara();
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
    else if (d.tipo === "zitto") zittisci(d.secondi);
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
  Fila.timbra(d, performance.now());       // 0.6.3: scadenza e chiave (web/fila.js)
  coda = Fila.togliChiave(coda, d);
  const soglia = d.categoria === "spotter" ? 2 : 3;   // lo spotter taglia anche la priorità 2
  if (d.interrompi && inOnda && inOnda.priorita >= soglia) {
    audio.pause();
    const tagliata = inOnda;
    inOnda = null;
    coda = coda.filter((x) => x.priorita < 3);
    if (tagliata.priorita === 2) coda.push(tagliata);   // una frase importante tagliata dallo spotter si ridice
    coda.unshift(d);
  } else {
    coda.push(d);
  }
  suonaProssima();
}

// il tasto del silenzio (UDP Action): smette subito di parlare, restano solo le frasi urgenti
function zittisci(secondi) {
  if (!secondi) return;
  if (inOnda && inOnda.priorita > 1) { audio.pause(); inOnda = null; }
  coda = coda.filter((x) => x.priorita <= 1);
  suonaProssima();
}

function suonaProssima() {
  if (inOnda || !coda.length || !collegato) return;
  coda = Fila.pulisci(coda, performance.now());   // le frasi del momento scadute non si leggono
  if (!coda.length) return;
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
  ultimoPistaLive = s.connesso && s.pista_id != null ? s.pista_id : null;
  if (s.connesso) {
    p.textContent = `PS5 collegata · ${s.sessione || ""}${s.pista ? " · " + s.pista : ""}${s.in_pausa ? " · in pausa" : ""}${s.silenzio ? " · silenzio radio" : ""}${s.zitta ? ` · radio zitta ${s.zitta} s` : ""}`;
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
  const deltaEl = $("#c-delta"), deltaFill = $("#delta-fill");
  if (a.delta != null) {
    const d = a.delta;
    const segno = d > 0 ? "+" : (d < 0 ? "−" : "");
    deltaEl.textContent = `${segno}${Math.abs(d).toFixed(2)} s`;
    deltaEl.className = d < 0 ? "veloce" : (d > 0 ? "lento" : "");
    const w = Math.min(50, (Math.abs(d) / 2.0) * 50);
    deltaFill.style.width = w.toFixed(1) + "%";
    deltaFill.style.left = d <= 0 ? "50%" : (50 - w).toFixed(1) + "%";
    deltaFill.className = "delta-fill " + (d < 0 ? "veloce" : (d > 0 ? "lento" : ""));
  } else {
    deltaEl.textContent = "–"; deltaEl.className = "";
    deltaFill.style.width = "0"; deltaFill.className = "delta-fill";
  }
  const bat = a.batteria != null ? Math.max(0, Math.min(100, a.batteria)) : 0;
  $("#ers-fill").style.width = a.batteria != null ? bat + "%" : "0";
  $("#ers-fill").className = "ers-fill" + (a.overtake_attivo ? " attivo" : (bat < 15 && a.batteria != null ? " basso" : ""));
  const ersParti = [];
  if (a.batteria != null) ersParti.push(a.batteria + "%");
  if (a.ers_modo) ersParti.push(a.ers_modo);
  if (a.overtake_attivo) ersParti.push("OVERTAKE ATTIVO");
  else if (a.overtake_disp) ersParti.push("Overtake pronto");
  const ersInfo = $("#c-ers-info");
  ersInfo.textContent = ersParti.length ? ersParti.join(" · ") : "–";
  ersInfo.className = "ers-badge" + (a.overtake_attivo ? " attivo" : (a.overtake_disp ? " pronto" : ""));
  const pianoBox = $("#piano-box");
  if (pianoBox) {
    if (a.piano && a.piano.attivo) {
      pianoBox.hidden = false;
      $("#c-piano-attivo").textContent = "Piano " + a.piano.attivo;
      $("#c-piano-dettaglio").textContent = `${a.piano.stile || ""}${a.piano.target_giro ? " · target box giro " + a.piano.target_giro : ""}`;
    } else {
      pianoBox.hidden = true;
    }
  }
  for (let k = 0; k < 4; k++) {
    const r = a.ruote && a.ruote[k];
    const card = $(`#ruote .ruota[data-r="${k}"]`);
    if (!card) continue;
    const uEl = card.querySelector(".r-usura"), tEl = card.querySelector(".r-temp"), bEl = card.querySelector(".r-blister");
    if (!r) {
      uEl.textContent = "–"; uEl.className = "r-usura";
      tEl.textContent = "–"; tEl.className = "r-temp";
      bEl.textContent = "";
      continue;
    }
    uEl.textContent = r.usura != null ? r.usura + "%" : "–";
    uEl.className = "r-usura" + (r.usura >= 70 ? " critico" : (r.usura >= 45 ? " avviso" : ""));
    tEl.textContent = (r.ts != null || r.ti != null) ? `S ${r.ts ?? "–"}° · I ${r.ti ?? "–"}°` : "–";
    tEl.className = "r-temp" + ((r.ti >= 110 || r.ts >= 115) ? " caldo" : (r.ti != null && r.ti > 0 && r.ti < 70 ? " freddo" : ""));
    bEl.textContent = r.blister > 0 ? `Blister ${r.blister}%` : "";
  }
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
  disegnaLivelli(v.verbosita);
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
  const maxC = v.max_consigli_guida ?? 12;
  $("#max_consigli_guida").value = maxC;
  $("#o-max_consigli").textContent = maxC ? maxC : "illimitati";
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
$("#max_consigli_guida").addEventListener("input", (e) => ($("#o-max_consigli").textContent = +e.target.value ? e.target.value : "illimitati"));
$("#max_consigli_guida").addEventListener("change", (e) => salva({ max_consigli_guida: +e.target.value }));

// ---------- che cosa aggiunge ogni livello (letto dal codice dal server: livelli.py) ----------
function disegnaLivelli(attivo) {
  const box = $("#livelli");
  const liv = impostazioni.livelli || {};
  const nomi = { 1: ["Essenziale", "solo l'indispensabile"], 2: ["Normale", "in più"], 3: ["Tutto", "in più"] };
  box.textContent = "";
  [1, 2, 3].forEach((n) => {
    const voci = liv[String(n)] || [];
    const d = document.createElement("div");
    d.className = "livello" + (n === attivo ? " attivo" : "") + (n > attivo ? " spento" : "");
    const b = document.createElement("b"); b.textContent = nomi[n][0];
    const t = document.createElement("span"); t.textContent = ` ${nomi[n][1]}: ${voci.join(", ") || "–"}.`;
    d.append(b, t);
    box.append(d);
  });
}

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
    if (st.piano_attivo) riga(s, `Piano attivo: Piano ${st.piano_attivo}.`);
    riga(s, `Tempo perso al box: ${st.perdita_box_s} s (${st.misurata ? "misurato su questa pista" : "stima generica, ancora nessuna misura"}).`);
    if (st.degrado_s_per_giro != null) riga(s, `Le tue gomme perdevano circa ${st.degrado_s_per_giro.toFixed(2)} s a giro.`);
    if (st.target_lap) riga(s, `Tempo obiettivo prima della sosta: ${st.target_lap} (per arrivare al giro ${st.target_lap_giro}).`);
  }
  if (r.confronto_riferimento) {
    const cr = r.confronto_riferimento;
    const s = scheda(cr.tipo === "compagno" ? "Confronto con il compagno" : "Confronto con riferimento", box);
    riga(s, `Riferimento: ${cr.pilota} · giro ${cr.giro} (${cr.tempo}).`);
    if (cr.peggiori && cr.peggiori.length)
      riga(s, "Dove perdi di più: " + cr.peggiori.map((c) => `${String(c.curva).includes(" e ") ? "curve" : "curva"} ${c.curva} (+${c.delta_s.toFixed(2)} s)`).join(" · "));
    tabella(s, ["Curva", "Delta s", "Frenata m", "V min km/h", "Gas m", "Nota"],
      (cr.curve || []).map((c) => [
        c.curva,
        c.delta_s == null ? null : (c.delta_s > 0 ? "+" : "") + c.delta_s.toFixed(2),
        c.frenata_diff_m == null ? null : (c.frenata_diff_m > 0 ? "+" : "") + c.frenata_diff_m,
        c.vmin_diff_kmh == null ? null : (c.vmin_diff_kmh > 0 ? "+" : "") + c.vmin_diff_kmh,
        c.gas_diff_m == null ? null : (c.gas_diff_m > 0 ? "+" : "") + c.gas_diff_m,
        c.nota,
      ]));
  }
  if (r.stacco_partenza) {
    const sp = r.stacco_partenza;
    const s = scheda("Stacco partenza", box);
    const num = document.createElement("div");
    num.className = "numeri";
    [
      ["Reazione", sp.tempo_reazione_s != null ? sp.tempo_reazione_s.toFixed(2) + " s" : "–"],
      ["Gas lancio", sp.gas_partenza_percento != null ? sp.gas_partenza_percento + "%" : "–"],
      ["Frizione", sp.frizione_usata ? (sp.rilascio_frizione_s != null ? sp.rilascio_frizione_s.toFixed(2) + " s" : "sì") : "no"],
      ["Pattin. max", sp.pattinamento_max != null ? sp.pattinamento_max.toFixed(2) : "–"],
      ["0–100 km/h", sp.tempo_0_100_s != null ? sp.tempo_0_100_s.toFixed(2) + " s" : "–"],
      ["Posizioni", sp.posizioni_guadagnate != null ? (sp.posizioni_guadagnate > 0 ? "+" + sp.posizioni_guadagnate : String(sp.posizioni_guadagnate)) : "–"],
    ].forEach(([k, v]) => { const d = document.createElement("div"); d.innerHTML = "<b></b><span></span>"; d.querySelector("b").textContent = v; d.querySelector("span").textContent = k; num.append(d); });
    s.append(num);
    if (sp.consiglio) {
      const c = document.createElement("div"); c.className = "consiglio"; c.textContent = sp.consiglio; s.append(c);
    }
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

// ---------- pre-gara ----------
async function caricaPregara(forzaPista) {
  const res = await (await fetch("/api/pregara")).json();
  const sel = $("#pg-pista");
  const prima = forzaPista ?? (sel.value || null);
  sel.innerHTML = "";
  const piste = res.piste || [];
  if (!piste.length) {
    $("#pg-vuoto").hidden = false;
    $("#pg-contenuto").hidden = true;
    return;
  }
  $("#pg-vuoto").hidden = true;
  $("#pg-contenuto").hidden = false;
  piste.forEach((p) => {
    const o = document.createElement("option");
    o.value = p.pista;
    o.textContent = p.giri ? `${p.nome} (${p.giri} giri)` : p.nome;
    sel.append(o);
  });
  let scelta = null;
  if (prima != null && piste.some((p) => String(p.pista) === String(prima))) scelta = String(prima);
  else if (ultimoPistaLive != null && piste.some((p) => String(p.pista) === String(ultimoPistaLive))) scelta = String(ultimoPistaLive);
  else if (res.corrente != null && piste.some((p) => String(p.pista) === String(res.corrente))) scelta = String(res.corrente);
  else scelta = String(piste[0].pista);
  sel.value = scelta;
  if (res.dati && String(res.corrente) === scelta) disegnaPregara(res.dati);
  else await caricaDettaglioPregara(scelta);
}

async function caricaDettaglioPregara(pista) {
  if (!pista) return;
  const r = await fetch("/api/pregara/" + encodeURIComponent(pista));
  if (!r.ok) return;
  disegnaPregara(await r.json());
}

function disegnaPregara(d) {
  // 1. Piano di gara A / B / C
  const boxPiani = $("#pg-piani");
  boxPiani.innerHTML = "<h3>Piano di gara pre-partenza</h3>";
  const piani = d.piani || {};
  const fonteMap = { sessione: "in sessione", storico: "da storico gare", stima: "stima indicativa" };
  riga(boxPiani, `Pista: ${d.nome} · Fonte: ${fonteMap[piani.fonte] || piani.fonte || "stima"} · Perdita box: ${t(piani.perdita_box_s)} s (${piani.misurata ? "misurata" : "stima"}).`).className = "nota";
  const grigliaP = document.createElement("div");
  grigliaP.className = "piani-riga";
  ["A", "B", "C"].forEach((cod) => {
    const p = (piani.piani || {})[cod];
    if (!p) return;
    const attivo = piani.attivo === cod;
    const card = document.createElement("div");
    card.className = "piano-card" + (attivo ? " attivo" : "");
    const testa = document.createElement("div");
    testa.className = "piano-card-testa";
    const h4 = document.createElement("b");
    h4.textContent = `${p.nome} · ${p.stile}`;
    testa.append(h4);
    if (attivo) {
      const badge = document.createElement("span");
      badge.className = "piano-badge";
      badge.textContent = "ATTIVO";
      testa.append(badge);
    }
    const meta = document.createElement("p");
    meta.className = "piano-meta";
    const fin = p.finestra
      ? (p.finestra[0] === p.finestra[1] ? `Finestra: giro ${p.finestra[0]}` : `Finestra: giri ${p.finestra[0]}–${p.finestra[1]}`)
      : "Finestra: da definire";
    meta.textContent = `${p.soste} ${p.soste === 1 ? "sosta" : "soste"} · ${fin} · ${(p.mescole || []).join(" → ")}`;
    const desc = document.createElement("p");
    desc.textContent = p.descrizione || "";
    card.append(testa, meta, desc);
    grigliaP.append(card);
  });
  boxPiani.append(grigliaP);

  // 2. Setup consigliato
  const boxSetup = $("#pg-setup");
  boxSetup.innerHTML = "<h3>Setup consigliato</h3>";
  const su = d.setup || {};
  if (su.sessioni_usate) riga(boxSetup, `Aggregato da ${su.sessioni_usate} ${su.sessioni_usate === 1 ? "sessione" : "sessioni"} su ${d.nome}.`).className = "nota";
  if (su.consigli && su.consigli.length) {
    su.consigli.forEach((c) => {
      const div = document.createElement("div");
      div.className = "consiglio";
      div.innerHTML = "<span></span><small></small>";
      div.querySelector("span").textContent = (c.area ? c.area + ": " : "") + c.consiglio;
      div.querySelector("small").textContent = "Perché: " + c.dato;
      boxSetup.append(div);
    });
  } else {
    riga(boxSetup, "Nessun aggiustamento netto suggerito dai dati salvati.");
  }
  if (su.ultimo_assetto) {
    const a = su.ultimo_assetto;
    const righe = [
      ["Ali ant / post", `${t(a.ala_anteriore)} / ${t(a.ala_posteriore)}`],
      ["Differenziale (traz / ril)", `${t(a.differenziale_in_trazione)}% / ${t(a.differenziale_in_rilascio)}%`],
      ["Freni (press / ripart)", `${t(a.pressione_freni)}% / ${t(a.ripartizione_freni)}%`],
      ["Campanatura ant / post", `${t(a.campanatura_anteriore)} / ${t(a.campanatura_posteriore)}`],
      ["Pressioni gomme", Array.isArray(a.pressioni_gomme) ? a.pressioni_gomme.join(" / ") : "–"],
    ];
    tabella(boxSetup, ["Assetto di riferimento", "Valore"], righe);
  }
  if (su.nota) riga(boxSetup, su.nota).className = "nota";

  // 3. Analisi stacco partenza
  const boxPart = $("#pg-partenza");
  boxPart.innerHTML = "<h3>Stacco partenza</h3>";
  const pa = d.partenza || {};
  const cons = document.createElement("div");
  cons.className = "consiglio";
  cons.textContent = pa.consiglio || "Nessun dato di partenza disponibile.";
  boxPart.append(cons);
  if (pa.storico && pa.storico.length) {
    tabella(boxPart, ["Sessione", "Reazione", "Friz. / Gas", "Pattin.", "0–100", "Pos"],
      pa.storico.map((s) => [
        `${s.creato || ""} ${s.sessione || ""}`.trim(),
        s.tempo_reazione_s != null ? s.tempo_reazione_s.toFixed(2) + " s" : null,
        `${s.frizione_usata ? "sì" : "no"} / ${s.gas_partenza_percento ?? "–"}%`,
        s.pattinamento_max != null ? s.pattinamento_max.toFixed(2) : null,
        s.tempo_0_100_s != null ? s.tempo_0_100_s.toFixed(2) + " s" : null,
        s.posizioni_guadagnate != null ? (s.posizioni_guadagnate > 0 ? "+" + s.posizioni_guadagnate : String(s.posizioni_guadagnate)) : null,
      ]));
  }

  // 4. Mappa frenate per curva
  const boxFren = $("#pg-frenate");
  boxFren.innerHTML = "<h3>Mappa frenate per curva</h3>";
  const fr = d.frenate;
  if (!fr || !(fr.curve || []).length) {
    riga(boxFren, "Nessun giro salvato su questa pista per costruire la mappa frenate.").className = "nota";
    return;
  }
  const g = fr.giro || {};
  riga(boxFren, `Dal miglior giro salvato: ${g.tempo || "–"} (${g.pilota || "io"} · ${g.sessione || ""}) · Numerazione: ${fr.numerazione === "ufficiale" ? "ufficiale circuito" : "nostra"}.`).className = "nota";
  tabella(boxFren, ["Curva", "Frenata m", "V ingresso", "V min", "Marcia min", "Gas pieno m"],
    fr.curve.map((c) => [
      c.curva,
      c.frenata_m,
      c.vingresso != null ? c.vingresso + " km/h" : null,
      c.vmin != null ? c.vmin + " km/h" : null,
      c.marcia_min,
      c.gas_m,
    ]));
}

$("#pg-pista").addEventListener("change", (e) => caricaDettaglioPregara(e.target.value));
$("#pg-aggiorna").addEventListener("click", () => caricaPregara($("#pg-pista").value));

// ---------- avvio ----------
if (/^\d+\.\d+\.\d+\.\d+$/.test(location.hostname)) $("#ip-server").textContent = location.hostname;
caricaImpostazioni();
chiamaPronuncia();
apri();
{ const b = document.querySelector(`nav button[data-vista="${location.hash.slice(1)}"]`); if (b) b.click(); }
