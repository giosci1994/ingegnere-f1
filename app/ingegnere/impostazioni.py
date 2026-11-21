"""Le impostazioni, salvate sul server in un file JSON (dati/impostazioni.json)."""

import json
import os
import threading

# categoria -> (etichetta per la pagina, priorità di base: 1 più alta)
CATEGORIE = {
    "bandiere": ("Bandiere, contromano, bandiera rossa", 1),
    "safety_car": ("Safety car e VSC", 1),
    "box": ("Box, finestra pit, limitatore", 2),
    "penalita": ("Penalità e limiti della pista", 2),
    "gomme": ("Gomme: usura e temperature", 3),
    "carburante": ("Carburante", 3),
    "ers": ("Batteria e Overtake 2026", 3),
    "danni": ("Danni alla macchina", 3),
    "strategia": ("Strategia: undercut, overcut, dove esci dal box", 2),
    "meteo": ("Meteo e pioggia", 3),
    "distacchi": ("Distacchi davanti e dietro", 4),
    "posizioni": ("Sorpassi e posizioni", 4),
    "ali": ("Ali mobili 2026", 4),
    "giri": ("Giri mancanti, partenza, arrivo", 5),
    "record": ("Tempi sul giro e record personali", 5),
    "guida": ("Staccate e uscite di curva: come migliorare (rispetto al tuo giro migliore)", 5),
    "domande": ("Risposte alle domande dai tasti (UDP Action)", 2),
    "settori": ("Tempi di settore contro il tuo migliore (prove e qualifiche)", 5),
    "passo": ("Passo contro chi è davanti e dietro (gara)", 4),
    "spotter": ("Spotter: macchina affiancata a sinistra o a destra", 1),
}
# spente di partenza (si accendono dalla pagina)
SPENTE = {"spotter"}

VERBOSITA = {1: "essenziale", 2: "normale", 3: "tutto"}

PREDEFINITE = {
    "avvisi": {k: k not in SPENTE for k in CATEGORIE},
    "verbosita": 2,
    "volume": 100,          # percento, applicato all'audio sul server (l'iPhone ignora il volume della pagina)
    "voce": "riccardo",     # riccardo (maschile, leggera) o paola (femminile, più naturale)
    "velocita": 1.1,        # 1.0 normale; un po' più svelta, come alla radio
    "effetto_radio": 2,     # 0 niente, 1 leggero, 2 normale, 3 forte
    "registra": True,       # salva le sessioni vere per riprodurle
    "registra_motion": True,  # i pacchetti motion a 10 Hz (i motion ex, piccoli, sempre)
    "salva_giri": True,       # la traccia di ogni giro, per traiettoria e confronti
    "assetto": True,          # i consigli d'assetto nel riassunto
    "pilota": "io",           # chi guida: si salva con i giri, per confrontarli
    "max_registrazioni_mb": 2000,
    "silenzio_qualifica": True,   # nel giro lanciato in qualifica solo gli avvisi urgenti (priorità 1–2)
    "una_curva_alla_volta": True, # in prova: i consigli su una curva sola (la peggiore) finché migliora
    "max_consigli_guida": 12,     # tetto consigli di guida per sessione (0 = illimitati)
    "tasti": {},                  # UDP Action 1–12 -> domanda (domande.py); riempito sotto
}

# le domande che si possono fare con i tasti della PS5 (domande.py le risponde)
DOMANDE = {
    "strategia": "Strategia: finestra box, undercut, dove esci",
    "gomme": "Gomme: usura e temperature",
    "distacchi": "Distacchi davanti e dietro",
    "carburante": "Carburante",
    "danni": "Danni",
    "passo": "Com'è il passo (ultimo giro contro il migliore)",
    "ripeti": "Ripeti l'ultima frase",
    "dove_perdo": "Dove perdo? (le due curve peggiori dell'ultimo giro)",
    "silenzio": "Silenzio radio per 30 secondi (di nuovo: riaccende)",
}
# di partenza: le prime sette UDP Action (si cambiano dall'app)
TASTI_PREDEFINITI = {str(n): (list(DOMANDE)[n - 1] if n <= len(DOMANDE) else "") for n in range(1, 13)}
PREDEFINITE["tasti"] = dict(TASTI_PREDEFINITI)


class Impostazioni:
    def __init__(self, percorso):
        self.percorso = percorso
        self._lock = threading.Lock()
        self.valori = json.loads(json.dumps(PREDEFINITE))
        if os.path.exists(percorso):
            try:
                with open(percorso, encoding="utf-8") as f:
                    self._unisci(json.load(f))
            except (OSError, ValueError):
                pass

    def _unisci(self, nuovi):
        for k, v in nuovi.items():
            if k == "avvisi" and isinstance(v, dict):
                for c, on in v.items():
                    if c in CATEGORIE:
                        self.valori["avvisi"][c] = bool(on)
            elif k == "tasti" and isinstance(v, dict):
                for n, d in v.items():
                    if str(n) in self.valori["tasti"] and (d in DOMANDE or not d):
                        self.valori["tasti"][str(n)] = d or ""
            elif k in PREDEFINITE and k not in ("avvisi", "tasti"):
                tipo = type(PREDEFINITE[k])
                if tipo is bool and isinstance(v, str):     # «false» non deve diventare True
                    v = v.strip().lower() in ("1", "true", "sì", "si", "on")
                try:
                    v = tipo(v)
                except (TypeError, ValueError):
                    continue
                if k == "verbosita":
                    v = min(3, max(1, v))
                elif k == "volume":
                    v = min(200, max(0, v))
                elif k == "voce" and v not in ("riccardo", "paola"):
                    continue
                elif k == "velocita":
                    v = min(1.4, max(0.7, v))
                elif k == "effetto_radio":
                    v = min(3, max(0, v))
                elif k == "max_consigli_guida":
                    v = min(100, max(0, v))
                elif k == "pilota":
                    v = " ".join(v.split())[:24] or "io"
                self.valori[k] = v

    def aggiorna(self, nuovi):
        with self._lock:
            self._unisci(nuovi)
            tmp = self.percorso + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.valori, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.percorso)
        return self.valori

    def __getitem__(self, k):
        return self.valori[k]

    def get(self, k, default=None):
        return self.valori.get(k, default)

    def acceso(self, categoria):
        return self.valori["avvisi"].get(categoria, categoria not in SPENTE)

    def descrizione(self):
        return {
            "valori": self.valori,
            "categorie": [{"id": k, "etichetta": v[0], "priorita": v[1]}
                          for k, v in CATEGORIE.items()],
            "verbosita": VERBOSITA,
            "domande": DOMANDE,
            "livelli": _livelli(),
        }


_LIVELLI = None


def _livelli():
    """Che cosa si aggiunge a ogni livello di verbosità, letto dal codice una volta sola."""
    global _LIVELLI
    if _LIVELLI is None:
        from . import livelli
        try:
            _LIVELLI = livelli.descrizione()
        except (OSError, SyntaxError):
            _LIVELLI = {}
    return _LIVELLI
