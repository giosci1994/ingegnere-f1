"""La voce: Piper in locale (voci italiane) + l'effetto del team radio, fatto da noi.

L'effetto (niente audio preso dalle trasmissioni, niente voci di persone reali):
- bip sintetizzato all'inizio (aprire la radio) e due bip alla fine (chiuderla);
- filtro passa-banda da radio (circa 300–3400 Hz), con una piccola risonanza;
- saturazione morbida e compressione, come un microfono spinto;
- fruscio di fondo e due colpi di «squelch» all'apertura e alla chiusura.

Le frasi si salvano in una cache su disco (WAV mono 16 bit), con il nome dato dall'hash di
voce + impostazioni + testo: le frasi fisse si preparano all'avvio, quelle con i numeri al volo.
"""

import hashlib
import io
import os
import threading
import wave

import numpy as np

VERSIONE_EFFETTO = 3
VOCI = {
    "riccardo": "it_IT-riccardo-x_low.onnx",
    "paola": "it_IT-paola-medium.onnx",
}


def _bip(sr, freq, durata, ampiezza=0.32):
    n = int(sr * durata)
    tt = np.arange(n) / sr
    s = np.sin(2 * np.pi * freq * tt) + 0.25 * np.sin(2 * np.pi * 2 * freq * tt)
    attacco = max(1, int(sr * 0.004))
    inv = np.ones(n)
    inv[:attacco] = np.linspace(0, 1, attacco)
    inv[-attacco:] = np.linspace(1, 0, attacco)
    return (ampiezza * s * inv / 1.25).astype(np.float32)


def _passabanda(x, sr, basso, alto, risonanza=1.0):
    n = len(x)
    if n == 0:
        return x
    nfft = 1 << (n - 1).bit_length()
    X = np.fft.rfft(x, nfft)
    f = np.fft.rfftfreq(nfft, 1 / sr)
    # pendenze dolci (4° ordine circa) e una piccola risonanza intorno ai 2 kHz
    hp = 1 / np.sqrt(1 + (basso / np.maximum(f, 1)) ** 8)
    lp = 1 / np.sqrt(1 + (f / alto) ** 8)
    picco = 1 + (risonanza - 1) * np.exp(-((f - 2000) / 600) ** 2)
    y = np.fft.irfft(X * hp * lp * picco, nfft)[:n]
    return y.astype(np.float32)


def _rumore(sr, n, seme):
    rng = np.random.default_rng(seme)
    return rng.standard_normal(n).astype(np.float32)


def effetto_radio(voce, sr, intensita=2, seme=0):
    """voce: float32 in [-1, 1]. Restituisce float32 con l'effetto radio."""
    if intensita <= 0:
        pausa = np.zeros(int(sr * 0.08), np.float32)
        return np.concatenate([pausa, voce, pausa])
    forza = {1: 0.6, 2: 1.0, 3: 1.5}[intensita]
    v = voce / (np.max(np.abs(voce)) + 1e-6) * 0.9
    v = _passabanda(v, sr, 320, 3300 if intensita < 3 else 2900, risonanza=1 + 0.5 * forza)
    # saturazione morbida + compressione
    spinta = 1.5 + 2.5 * forza
    v = np.tanh(spinta * v) / np.tanh(spinta)
    v = v / (np.max(np.abs(v)) + 1e-6) * 0.85

    s = lambda d: int(sr * d)
    apri = _bip(sr, 1650, 0.11)
    chiudi = np.concatenate([_bip(sr, 1650, 0.07), np.zeros(s(0.03), np.float32), _bip(sr, 1250, 0.09)])
    squelch = 0.30 * forza
    pezzi = [
        np.zeros(s(0.05), np.float32), apri, np.zeros(s(0.06), np.float32),
        squelch * _rumore(sr, s(0.07), seme) * np.linspace(1, 0.2, s(0.07)).astype(np.float32),
        np.zeros(s(0.05), np.float32), v, np.zeros(s(0.10), np.float32),
        squelch * _rumore(sr, s(0.09), seme + 1) * np.linspace(0.3, 1, s(0.09)).astype(np.float32),
        chiudi, np.zeros(s(0.06), np.float32),
    ]
    tutto = np.concatenate(pezzi)
    # fruscio di fondo sotto tutta la frase, filtrato come la voce
    fruscio = _passabanda(_rumore(sr, len(tutto), seme + 2), sr, 400, 3800)
    fruscio *= (0.012 * forza) / (np.std(fruscio) + 1e-6)
    tutto = tutto + fruscio
    return np.clip(tutto, -1, 1).astype(np.float32)


def wav_bytes(campioni, sr):
    pcm = (np.clip(campioni, -1, 1) * 32767).astype("<i2").tobytes()
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return b.getvalue()


def scala_volume(dati_wav, volume):
    """Applica il volume (percento) a un WAV 16 bit, senza toccare il file in cache."""
    if volume == 100:
        return dati_wav
    with wave.open(io.BytesIO(dati_wav)) as w:
        sr, fr = w.getframerate(), w.readframes(w.getnframes())
    x = np.frombuffer(fr, "<i2").astype(np.float32) / 32767 * (volume / 100)
    return wav_bytes(x, sr)


def durata_wav(percorso):
    with wave.open(percorso) as w:
        return w.getnframes() / w.getframerate()


class Voce:
    def __init__(self, cartella_voci, cartella_cache):
        self.cartella_voci = cartella_voci
        self.cache = cartella_cache
        os.makedirs(cartella_cache, exist_ok=True)
        self._voci = {}
        self._lock = threading.Lock()   # Piper una frase alla volta: il server è piccolo

    def _carica(self, nome):
        if nome not in self._voci:
            os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
            import onnxruntime
            if hasattr(onnxruntime, "disable_telemetry_events"):
                onnxruntime.disable_telemetry_events()   # i dati restano a casa
            from piper import PiperVoice
            self._voci[nome] = PiperVoice.load(os.path.join(self.cartella_voci, VOCI[nome]))
        return self._voci[nome]

    def chiave(self, testo, voce, velocita, effetto):
        h = hashlib.sha1(f"{VERSIONE_EFFETTO}|{voce}|{velocita:.2f}|{effetto}|{testo}".encode()).hexdigest()
        return h[:20]

    def percorso(self, chiave):
        return os.path.join(self.cache, chiave + ".wav")

    def sintetizza(self, testo, voce="riccardo", velocita=1.0, effetto=2):
        """Restituisce (chiave, durata in secondi). Blocca: va chiamata in un thread."""
        k = self.chiave(testo, voce, velocita, effetto)
        p = self.percorso(k)
        if os.path.exists(p):
            return k, durata_wav(p)
        with self._lock:
            if os.path.exists(p):
                return k, durata_wav(p)
            v = self._carica(voce)
            campioni, sr = self._piper(v, testo, velocita)
            seme = int(k[:6], 16)
            audio = effetto_radio(campioni, sr, effetto, seme)
            tmp = p + ".tmp"
            with open(tmp, "wb") as f:
                f.write(wav_bytes(audio, sr))
            os.replace(tmp, p)
        return k, len(audio) / sr

    @staticmethod
    def _piper(v, testo, velocita):
        from piper import SynthesisConfig
        cfg = SynthesisConfig(length_scale=1.0 / max(0.5, velocita))
        pezzi, sr = [], v.config.sample_rate
        for c in v.synthesize(testo, syn_config=cfg):
            pezzi.append(np.asarray(c.audio_float_array, dtype=np.float32))
            sr = c.sample_rate
            pezzi.append(np.zeros(int(sr * 0.12), np.float32))   # respiro tra le frasi
        if not pezzi:
            return np.zeros(int(sr * 0.2), np.float32), sr
        return np.concatenate(pezzi[:-1]), sr

    def pulisci_cache(self, max_file=3000):
        file = sorted((os.path.join(self.cache, f) for f in os.listdir(self.cache)
                       if f.endswith(".wav")), key=os.path.getmtime)
        for f in file[:-max_file]:
            try:
                os.remove(f)
            except OSError:
                pass
