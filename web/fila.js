// Ingegnere F1 · le regole della fila del telefono (0.6.3), senza pagina: le usa app.js e le
// prova node (prove/prova_fila.js).
// - una frase che arriva con `scade_tra` (secondi; il server lo mette solo alle categorie del
//   momento: posizioni, distacchi, spotter, ali, passo, settori) scade al telefono dopo quel
//   tempo più un margine: se il telefono è indietro, non la legge più;
// - una frase nuova con la stessa chiave toglie dalla fila quella vecchia;
// - le urgenti (priorità 0–1) restano come prima: niente scadenza, niente sostituzione.
"use strict";

const Fila = {
  MARGINE_MS: 1000,

  // al suo arrivo: quando scade, in millisecondi dell'orologio del telefono
  timbra(d, adesso) {
    d.scade = d.priorita > 1 && typeof d.scade_tra === "number" ? adesso + d.scade_tra * 1000 : null;
    return d;
  },

  scaduta(d, adesso) {
    return d.priorita > 1 && d.scade != null && adesso > d.scade + Fila.MARGINE_MS;
  },

  // la fila senza le frasi con la stessa chiave di `d` (non urgenti)
  togliChiave(coda, d) {
    if (d.priorita <= 1 || !d.chiave) return coda;
    return coda.filter((x) => x.priorita <= 1 || x.chiave !== d.chiave);
  },

  // la fila senza le frasi scadute
  pulisci(coda, adesso) {
    return coda.filter((x) => !Fila.scaduta(x, adesso));
  },
};

if (typeof module !== "undefined") module.exports = Fila;
