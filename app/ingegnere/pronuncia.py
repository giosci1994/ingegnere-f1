"""Il dizionario di pronuncia: prima di Piper, ogni frase passa da una tabella di sostituzioni.

- Parole intere (anche di più parole, «safety car»), senza distinzione di maiuscole; si prova
  prima la voce più lunga, così «virtual safety car» vince su «safety car».
- La tabella di partenza (BASE) sta qui; le modifiche dell'utente stanno in
  `dati/pronuncia.json` (sopravvivono ai rifacimenti del container): `{"voci": {parola: grafia},
  "tolte": [parola, ...]}`. Una voce sua con la stessa parola vince su quella di partenza.
- La cache dei WAV usa il testo già sostituito (voce.py): cambiare una voce = audio nuovo.

Le grafie sono scelte ascoltando la voce `riccardo` (Piper, fonemi di espeak-ng in italiano) e
facendo trascrivere le prove a whisper: l'accento grave/acuto dice a espeak dove cade l'accento
(«Monreàl»), e si scrivono all'italiana le lettere che in inglese o in francese sono mute
(«Leclèr», non «Leclerc» con la c finale letta).
"""

import json
import os
import re
import threading

BASE = {
    # termini inglesi della radio
    "safety car": "séifti car",
    "virtual": "vìrciual",
    "undercut": "àndercat",
    "overcut": "òvercat",
    "pit lane": "pit léin",
    "DRS": "di erre esse",
    "ERS": "e erre esse",
    "overtake": "overtéik",
    "lift and coast": "lift end còust",
    "blistering": "blìsterin",
    "brake bias": "bréik bàias",
    "track limits": "trèk lìmits",
    "MGU-K": "emme gi u cappa",
    "MGU-H": "emme gi u acca",
    # piloti 2026 (dal pacchetto participants delle gare vere del 20/11/2026)
    "Hadjar": "Agiàr",
    "Russell": "Ràssel",
    "Leclerc": "Leclèr",
    "Hamilton": "Hèmilton",
    "Gasly": "Gaslì",
    "Sainz": "Sàins",
    "Lawson": "Lòsson",
    "Ocon": "Ocòn",
    "Bearman": "Bìrman",
    "Hulkenberg": "Hùlkenberg",
    "Hülkenberg": "Hùlkenberg",
    "Pérez": "Pères",
    # squadre
    "McLaren": "Mac Làren",
    "Alpine": "Alpìn",
    "Racing Bulls": "Rèissing Bulls",
    "Haas": "Has",
    # piste
    "Montréal": "Monreàl",
    "Shanghai": "Sciangài",
    "Austin": "Òstin",
    "Spielberg": "Spìlberg",
    "Baku": "Bakù",
    "Zandvoort": "Zàndvort",
    "Jeddah": "Gedda",
    "Losail": "Losàil",
    "Melbourne": "Mèlburn",
    "Spa": "Spà",                  # senza: «esse pi a», letta come una sigla
    "Hungaroring": "Ungaroring",
}

MAX_VOCI = 300


def _norm(parola):
    return " ".join(str(parola).split())[:40]


class Pronuncia:
    def __init__(self, percorso):
        self.percorso = percorso
        self._lock = threading.Lock()
        self.mie = {}            # parola -> grafia (dell'utente)
        self.tolte = set()       # parole di partenza tolte (minuscole)
        if percorso and os.path.exists(percorso):
            try:
                with open(percorso, encoding="utf-8") as f:
                    d = json.load(f)
                self.mie = {_norm(k): _norm(v) for k, v in (d.get("voci") or {}).items() if _norm(k)}
                self.tolte = {_norm(x).lower() for x in d.get("tolte") or []}
            except (OSError, ValueError, AttributeError):
                pass
        self._ricompila()

    # ---------- la tabella ----------
    def tabella(self):
        """{parola minuscola: (parola, grafia)}: partenza meno le tolte, più le mie."""
        out = {}
        for k, v in BASE.items():
            if k.lower() not in self.tolte:
                out[k.lower()] = (k, v)
        for k, v in self.mie.items():
            out[k.lower()] = (k, v)
        return out

    def _ricompila(self):
        t = self.tabella()
        self._mappa = {k: v for k, (_, v) in t.items()}
        if not t:
            self._re = None
            return
        chiavi = sorted(t, key=len, reverse=True)
        self._re = re.compile(r"(?<!\w)(" + "|".join(re.escape(k) for k in chiavi) + r")(?!\w)",
                              re.IGNORECASE)

    def applica(self, testo):
        if not self._re:
            return testo
        return self._re.sub(lambda m: self._mappa.get(m.group(0).lower(), m.group(0)), testo)

    def firma(self):
        """Cambia quando cambia la tabella (per sapere se rifare le frasi fisse)."""
        return hash(tuple(sorted(self._mappa.items())))

    # ---------- per la pagina ----------
    def elenco(self):
        out = []
        for k, (parola, grafia) in sorted(self.tabella().items()):
            base = next((v for b, v in BASE.items() if b.lower() == k), None)
            mia = any(m.lower() == k for m in self.mie)
            origine = "partenza" if not mia else ("cambiata" if base is not None else "mia")
            out.append({"parola": parola, "grafia": grafia, "origine": origine, "partenza": base})
        tolte = [{"parola": b, "grafia": v, "origine": "tolta", "partenza": v}
                 for b, v in BASE.items() if b.lower() in self.tolte and b.lower() not in
                 {m.lower() for m in self.mie}]
        return out + sorted(tolte, key=lambda x: x["parola"].lower())

    def metti(self, parola, grafia):
        parola, grafia = _norm(parola), _norm(grafia)
        if not parola or not grafia:
            raise ValueError("parola e grafia servono tutte e due")
        with self._lock:
            for k in [k for k in self.mie if k.lower() == parola.lower()]:
                del self.mie[k]
            if len(self.mie) >= MAX_VOCI:
                raise ValueError("troppe voci")
            self.mie[parola] = grafia
            self.tolte.discard(parola.lower())
            self._salva()

    def togli(self, parola):
        """Una voce mia torna come quella di partenza (se c'è); una di partenza si toglie."""
        parola = _norm(parola)
        with self._lock:
            mie = [k for k in self.mie if k.lower() == parola.lower()]
            for k in mie:
                del self.mie[k]
            if not mie and any(b.lower() == parola.lower() for b in BASE):
                self.tolte.add(parola.lower())
            self._salva()

    def rimetti(self, parola):
        """Rimette una voce di partenza tolta."""
        with self._lock:
            self.tolte.discard(_norm(parola).lower())
            self._salva()

    def _salva(self):
        self._ricompila()
        if not self.percorso:
            return
        tmp = self.percorso + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"voci": self.mie, "tolte": sorted(self.tolte)}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.percorso)
