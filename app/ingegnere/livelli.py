"""Che cosa dice l'ingegnere a ogni livello di verbosità (1 essenziale, 2 normale, 3 tutto).

Il livello di ogni frase non si ricopia a mano: si legge dal codice (`ast`), dalle chiamate
`Messaggio(...)` e `self._m(...)` (argomento `livello`) e dalle parti del riepilogo del giro
(`parti.append((categoria, livello, testo))`). Qui c'è solo il nome in parole di ogni frase,
per categoria e chiave (la parte fissa all'inizio della chiave). Se nel codice compare una
frase senza nome qui, `mancanti()` la dice (la prova `prove/prova_fase3.py` fallisce).

Le spunte degli avvisi scelgono gli argomenti; il livello dice quanto se ne parla dentro ogni
argomento acceso: a «Normale» si sente anche tutto quello di «Essenziale», a «Tutto» anche
quello di «Normale».
"""

import ast
import os

CARTELLA = os.path.dirname(os.path.abspath(__file__))
FILE = ("ingegnere.py", "analisi.py", "domande.py", "server.py", "gara.py", "spotter.py")

# "categoria:chiave" -> nome della frase; "categoria:chiave@livello" quando la stessa chiave ha
# frasi diverse a livelli diversi
ETICHETTE = {
    "bandiere:contromano": "contromano",
    "bandiere:gialla": "bandiere gialla, blu e rossa",
    "bandiere:blu": "bandiere gialla, blu e rossa",
    "bandiere:rossa": "bandiere gialla, blu e rossa",
    "bandiere:verde": "bandiera verde",
    "safety_car:sc": "safety car e VSC (e il delta)",
    "safety_car:vsc": "safety car e VSC (e il delta)",
    "safety_car:vsc_fine": "safety car e VSC (e il delta)",
    "safety_car:delta": "safety car e VSC (e il delta)",
    "safety_car:sc_rientra": "safety car e VSC (e il delta)",
    "safety_car:sc_via": "safety car e VSC (e il delta)",
    "box:limitatore": "limitatore",
    "box:finestra": "finestra box e ultimo giro utile",
    "box:ultimo_utile": "finestra box e ultimo giro utile",
    "box:box_gomme": "box per gomme finite o ala rotta",
    "box:box_ala": "box per gomme finite o ala rotta",
    "box:uscita_box": "uscita dai box con la posizione",
    "penalita:pen": "penalità",
    "penalita:squalifica": "penalità",
    "penalita:avvertimento": "avvertimenti per i limiti",
    "penalita:invalido": "giro cancellato (prove e qualifiche)",
    "penalita:scontata": "penalità scontata",
    "gomme:usura@1": "gomme al 70 e all'80 per cento",
    "gomme:usura@2": "usura gomme al 55 per cento",
    "gomme:usura@3": "usura gomme al 40 per cento",
    "gomme:usura70": "gomme al 70 e all'80 per cento",
    "gomme:blister": "blistering",
    "gomme:gomme_calde": "gomme surriscaldate",
    "gomme:gomme_fredde": "gomme fredde",
    "gomme:freni": "freni caldi",
    "carburante:benzina_poca": "carburante che non basta",
    "ers:batteria": "batteria quasi scarica",
    "ers:overtake": "overtake disponibile",
    "danni:danno_@1": "danni a motore e cambio, guasto ERS",
    "danni:guasto_ers": "danni a motore e cambio, guasto ERS",
    "danni:danno_@2": "danni ad ali, fondo, diffusore e pance, guasto DRS",
    "danni:guasto_drs": "danni ad ali, fondo, diffusore e pance, guasto DRS",
    "danni:contatto": "contatti",
    "strategia:undercut": "undercut, overcut e soste degli altri",
    "strategia:sosta_altri": "undercut, overcut e soste degli altri",
    "strategia:rientro": "dove esci se ti fermi adesso",
    "meteo:previsione": "pioggia in arrivo, intermedie o slick",
    "meteo:intermedie": "pioggia in arrivo, intermedie o slick",
    "meteo:slick": "pioggia in arrivo, intermedie o slick",
    "meteo:pioggia_ora": "inizia a piovere",
    "distacchi:attacca": "sotto il secondo: attacca o difendi",
    "distacchi:difendi": "sotto il secondo: attacca o difendi",
    "riepilogo:distacchi@2": "distacchi davanti e dietro ogni due giri",
    "riepilogo:distacchi@3": "distacchi davanti e dietro a ogni giro",
    "posizioni:giro1": "posizione a fine primo giro",
    "posizioni:posizione": "sorpassi fatti e subiti",
    "ali:ali_pista": "ali mobili",
    "ali:ali_rettilineo": "ali mobili",
    "giri:via": "partenza («via»)",
    "giri:saluto": "radio check all'inizio",
    "giri:ultimo_giro": "ultimo giro e bandiera a scacchi",
    "giri:arrivo": "ultimo giro e bandiera a scacchi",
    "giri:mancano": "giri che mancano (10, 5, 3)",
    "giri:meta": "metà gara",
    "giri:tempo": "minuti alla fine della sessione",
    "giri:riassunto": "riassunto pronto",
    "record:giro_veloce": "giro più veloce della gara",
    "record:best": "giro veloce personale",
    "record:tempo": "tempo di ogni giro in prova e qualifica",
    "riepilogo:record": "tempo di ogni giro in gara",
    "riepilogo:carburante": "margine di carburante a fine giro",
    "guida:curva": "consigli di guida dopo le curve",
    "guida:fuoco": "consigli di guida dopo le curve",
    "domande:domanda_": "risposte ai tasti (UDP Action)",
    "domande:domanda_ripeti": "risposte ai tasti (UDP Action)",
    # fase 5 (gara.py, spotter.py)
    "strategia:box_sc": "box sotto safety car o VSC",
    "strategia:mescola": "quale set montare al box",
    "settori:settore": "tempi di settore (prove e qualifiche)",
    "passo:passo": "passo contro chi è davanti e dietro",
    "carburante:prev_benzina@1": "carburante a giro per arrivare in fondo",
    "carburante:prev_benzina@3": "con quanto carburante arrivi",
    "gomme:prev_usura@2": "quando le gomme arrivano all'80 per cento",
    "gomme:prev_usura@3": "con che usura finisci la gara",
    "spotter:spotter": "spotter: macchina affiancata",
    "spotter:spotter_libero": "spotter: «libero»",
    # fase 6 · blocco 1
    "bandiere:doppiaggio": "auto doppiata davanti",
    "penalita:avvertimento_ultimo": "ultimo avvertimento track limits prima della penalità",
    "ers:lift_coast_ers": "lift and coast quando la batteria è bassa",
    "ers:ers_attacco": "quando usare l'ERS in attacco",
    "ers:ers_difesa": "quando usare l'ERS in difesa",
    "carburante:lift_coast_fuel": "lift and coast per risparmiare carburante",
    "danni:motore_caldo": "motore surriscaldato",
    "danni:aria_pulita": "prendere aria pulita in scia",
    "danni:usura_pu": "usura alta di motore, turbo, ERS o cambio",
    "danni:usura_pu_critica": "usura critica di motore, turbo, ERS o cambio",
    "record:giro_veloce_altri": "giro più veloce degli avversari",
    "gomme:brake_bias": "consigli sulla ripartizione di frenata",
    "strategia:sosta_gomma": "soste degli avversari e gomme montate",
    "strategia:target_lap": "tempo obiettivo per gestire le gomme",
    "passo:settore_altro": "settori contro chi è davanti e dietro",
    # fase 6 · blocco 2
    "strategia:piano_strategia": "cambio piano di strategia (A, B, C)",
    "strategia:resta_fuori": "chiamata «resta fuori» se cambia la situazione",
    "box:box_questo_giro": "chiamata «box questo giro» sul giro target",
    "box:box_pioggia": "chiamata «box questo giro» per intermedie o bagnato con la pioggia in pista",
    "guida:confronto_ext": "consigli di guida dal confronto con compagno o leader",
}

# livelli che nel codice sono una variabile: si scrivono qui (e la prova li controlla)
VARIABILI = {
    "gomme:usura": (1, 2, 3),          # soglie 70/80 → 1, 55 → 2, 40 → 3 (`_gomme`)
    "riepilogo:distacchi": (2, 3),     # ogni due giri → 2, a ogni giro → 3 (`_giro`)
}


def _testo(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (str, int)):
        return n.value
    if isinstance(n, ast.JoinedStr):            # f"curva{...}" → "curva"
        pezzi = []
        for v in n.values:
            if not isinstance(v, ast.Constant):
                break
            pezzi.append(v.value)
        return "".join(pezzi)
    return None


def trova():
    """[(chiave «categoria:prefisso», livello o None se è una variabile, file:riga)] dal codice."""
    out = []
    for nome in FILE:
        with open(os.path.join(CARTELLA, nome), encoding="utf-8") as f:
            albero = ast.parse(f.read())
        for n in ast.walk(albero):
            if not isinstance(n, ast.Call):
                continue
            fun = getattr(n.func, "attr", getattr(n.func, "id", ""))
            if fun == "_msg" and nome == "spotter.py":     # Spotter._msg(chiave, testo, t, livello=1)
                chiave = _testo(n.args[0]) if n.args else None
                if isinstance(chiave, str):
                    liv = next((k.value for k in n.keywords if k.arg == "livello"), None)
                    out.append((f"spotter:{chiave}", liv.value if isinstance(liv, ast.Constant) else 1,
                                f"{nome}:{n.lineno}"))
                continue
            if fun in ("Messaggio", "_m"):
                a = n.args[2:] if fun == "_m" else n.args
                if len(a) < 2:
                    continue
                cat, chiave = _testo(a[0]), _testo(a[1])
                if not isinstance(cat, str) or not isinstance(chiave, str):
                    continue                    # i costruttori generici (categoria variabile)
                liv = next((k.value for k in n.keywords if k.arg == "livello"), None)
                livello = liv.value if isinstance(liv, ast.Constant) else (2 if liv is None else None)
                out.append((f"{cat}:{chiave}", livello, f"{nome}:{n.lineno}"))
            elif fun == "append" and n.args and isinstance(n.args[0], ast.Tuple) and len(n.args[0].elts) == 3:
                cat, liv, _ = n.args[0].elts
                if isinstance(cat, ast.Constant) and isinstance(cat.value, str):
                    livello = liv.value if isinstance(liv, ast.Constant) else None
                    out.append((f"riepilogo:{cat.value}", livello, f"{nome}:{n.lineno}"))
    return out


def _voci():
    """(livello, ordine della categoria, etichetta) per ogni frase trovata nel codice, con i
    livelli variabili espansi; le categorie nell'ordine degli avvisi della pagina."""
    from .impostazioni import CATEGORIE
    ordine = {c: i for i, c in enumerate(CATEGORIE)}
    for chiave, livello, _ in trova():
        livelli = VARIABILI.get(chiave, ()) if livello is None else (livello,)
        cat = chiave.split(":")[0]
        if cat == "riepilogo":
            cat = chiave.split(":")[1]
        for lv in livelli:
            et = ETICHETTE.get(f"{chiave}@{lv}") or ETICHETTE.get(chiave)
            if et:
                yield lv, ordine.get(cat, 99), et


def mancanti():
    """Le frasi del codice senza un nome qui, o con un livello variabile non scritto."""
    out = []
    for chiave, livello, dove in trova():
        livelli = VARIABILI.get(chiave) if livello is None else (livello,)
        if not livelli:
            out.append(f"{dove} {chiave}: livello variabile non in VARIABILI")
            continue
        for lv in livelli:
            if not (ETICHETTE.get(f"{chiave}@{lv}") or ETICHETTE.get(chiave)):
                out.append(f"{dove} {chiave} (livello {lv}): manca il nome")
    return out


def descrizione():
    """{1: [nomi], 2: [nomi in più], 3: [nomi in più]}, senza ripetere un nome già detto prima."""
    per = {1: [], 2: [], 3: []}
    for lv, _, et in sorted(_voci(), key=lambda x: (x[0], x[1])):
        if lv in per and not any(et in per[k] for k in per if k <= lv):
            per[lv].append(et)
    return per
