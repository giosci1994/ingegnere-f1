// Prova della fila del telefono (0.6.3, web/fila.js), senza pagina:  node prove/prova_fila.js
"use strict";
const path = require("path");
const Fila = require(path.join(__dirname, "..", "web", "fila.js"));
let problemi = 0;
const ok = (c, cosa) => { console.log((c ? "  ok  " : "  NO  ") + cosa); if (!c) problemi++; };

// scadenza: frase del momento con 2 s, letta a 2,5 s (margine 1 s) sì, a 3,5 s no
const p = Fila.timbra({ priorita: 4, chiave: "posizione", scade_tra: 2 }, 1000);
ok(p.scade === 3000, "timbra: scade = arrivo + scade_tra");
ok(!Fila.scaduta(p, 3500), "dentro il margine di 1 s non è scaduta");
ok(Fila.scaduta(p, 4100), "oltre il margine è scaduta");
// le urgenti e quelle senza scade_tra non scadono
const u = Fila.timbra({ priorita: 1, chiave: "spotter", scade_tra: 1 }, 0);
ok(u.scade === null && !Fila.scaduta(u, 1e9), "priorità 1: niente scadenza");
const g = Fila.timbra({ priorita: 3, chiave: "gomme", scade_tra: null }, 0);
ok(!Fila.scaduta(g, 1e9), "senza scade_tra (gomme): niente scadenza");
// pulisci
let coda = [p, u, g];
coda = Fila.pulisci(coda, 10000);
ok(coda.length === 2 && !coda.includes(p), "pulisci toglie solo la frase del momento scaduta");
// stessa chiave: la vecchia esce
const vecchia = Fila.timbra({ priorita: 4, chiave: "posizione", testo: "P 6", scade_tra: 5 }, 0);
const nuova = Fila.timbra({ priorita: 4, chiave: "posizione", testo: "P 5", scade_tra: 5 }, 100);
coda = Fila.togliChiave([vecchia, g], nuova);
coda.push(nuova);
ok(coda.length === 2 && coda.includes(nuova) && !coda.includes(vecchia), "stessa chiave: resta solo la nuova");
// urgenti con la stessa chiave: come prima (restano tutte e due)
const s1 = { priorita: 1, chiave: "spotter" }, s2 = { priorita: 1, chiave: "spotter" };
coda = Fila.togliChiave([s1], s2);
ok(coda.length === 1 && coda[0] === s1, "priorità 1: la stessa chiave non toglie niente");
// frasi di prova della pagina (priorità 0, senza chiave)
const prova = Fila.timbra({ priorita: 0, categoria: "prova" }, 0);
ok(!Fila.scaduta(prova, 1e9) && Fila.togliChiave([prova], prova).length === 1, "frasi di prova: invariate");
console.log("\nESITO:", problemi ? "NON VA" : "OK");
process.exit(problemi ? 1 : 0);
