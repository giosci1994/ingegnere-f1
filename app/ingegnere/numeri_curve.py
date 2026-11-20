'''Le curve con la numerazione ufficiale dei circuiti.

Per ogni pista (id del gioco) la tabella dà i numeri ufficiali delle curve e la loro posizione come
frazione del giro (0 = linea del traguardo, 1 = giro intero), da moltiplicare per la lunghezza
della pista del gioco.

**Fonte della tabella** [extra · MultiViewer]: `https://api.multiviewer.app/api/v1/circuits/<chiave>/2026`
(scaricata il 20/11/2026), che pubblica le curve («corners»: numero, lettera, distanza lungo il
tracciato) ricavate dai dati del live timing ufficiale F1; l'anno tra parentesi è quello del giro
usato per il tracciato. La frazione è la distanza della curva divisa per la lunghezza del
tracciato (chiuso). Madrid (id 42) e le piste inverse non ci sono: lì resta la nostra
numerazione (curve in ordine sul giro).

Le curve che troviamo noi (minimi di velocità, `curve.py`) sono di meno: una chicane è una curva
sola. Ogni nostra curva prende il numero ufficiale più vicino; se due curve ufficiali cadono
entrambe vicino all'apice (una chicane, una esse), prende tutte e due («curve 13 e 14»).
Tra il gioco e la realtà la linea del traguardo può essere spostata di qualche decina di metri:
lo spostamento si cerca da solo (tra -150 e +150 m) sulle curve del giro di riferimento.
Se dopo lo spostamento le curve non tornano (troppo lontane o con lo stesso numero), si resta
alla nostra numerazione.
'''

# id del gioco: (anno del tracciato, nome del circuito nella fonte, [(numero, frazione del giro)])
UFFICIALI = {
    0: (2022, 'Melbourne', [(1, 0.068), (2, 0.0834), (3, 0.206), (4, 0.2353), (5, 0.2734), (6, 0.355), (7, 0.376), (8, 0.4148), (9, 0.6263), (10, 0.648), (11, 0.7819), (12, 0.832), (13, 0.8788), (14, 0.91)]),
    2: (2019, 'Shanghai', [(1, 0.1054), (2, 0.1392), (3, 0.1673), (4, 0.1921), (5, 0.2474), (6, 0.2941), (7, 0.3787), (8, 0.4334), (9, 0.4685), (10, 0.4898), (11, 0.5774), (12, 0.593), (13, 0.6304), (14, 0.8812), (15, 0.8962), (16, 0.9505)]),
    3: (2022, 'Sakhir', [(1, 0.132), (2, 0.1496), (3, 0.1705), (4, 0.2798), (5, 0.3293), (6, 0.3468), (7, 0.3638), (8, 0.412), (9, 0.4795), (10, 0.4973), (11, 0.6419), (12, 0.7159), (13, 0.7566), (14, 0.907), (15, 0.9222)]),
    4: (2023, 'Catalunya', [(1, 0.1762), (2, 0.1938), (3, 0.2485), (4, 0.3715), (5, 0.4662), (6, 0.5062), (7, 0.5432), (8, 0.563), (9, 0.6209), (10, 0.7498), (11, 0.7822), (12, 0.8054), (13, 0.8655), (14, 0.9323)]),
    5: (2022, 'Monte Carlo', [(1, 0.0594), (2, 0.1786), (3, 0.2291), (4, 0.2673), (5, 0.3366), (6, 0.373), (7, 0.3972), (8, 0.4236), (9, 0.525), (10, 0.625), (11, 0.6409), (12, 0.7106), (13, 0.7573), (14, 0.7664), (15, 0.8073), (16, 0.8139), (17, 0.8364), (18, 0.8722), (19, 0.9)]),
    6: (2022, 'Montreal', [(1, 0.0519), (2, 0.0755), (3, 0.1624), (4, 0.1755), (5, 0.2273), (6, 0.2785), (7, 0.2987), (8, 0.4559), (9, 0.4745), (10, 0.6123), (11, 0.6366), (12, 0.7216), (13, 0.8871), (14, 0.8946)]),
    7: (2022, 'Silverstone', [(1, 0.0774), (2, 0.1045), (3, 0.1484), (4, 0.1776), (5, 0.2103), (6, 0.3359), (7, 0.3734), (8, 0.4323), (9, 0.5221), (10, 0.6166), (11, 0.6323), (12, 0.6571), (13, 0.6813), (14, 0.7063), (15, 0.8539), (16, 0.9311), (17, 0.9464), (18, 0.9721)]),
    9: (2021, 'Hungaroring', [(1, 0.1484), ('1A', 0.1912), (2, 0.2634), (3, 0.3051), (4, 0.4147), (5, 0.4702), (6, 0.5473), (7, 0.5573), (8, 0.5956), (9, 0.6277), (10, 0.6725), (11, 0.7182), (12, 0.8091), ('12A', 0.8384), (13, 0.8703), (14, 0.9373)]),
    10: (2021, 'Spa-Francorchamps', [(1, 0.0548), (2, 0.1524), (3, 0.1687), (4, 0.1828), (5, 0.3455), (6, 0.3569), (7, 0.3805), (8, 0.4369), (9, 0.4716), (10, 0.5457), (11, 0.5812), (12, 0.6417), (13, 0.6645), (14, 0.7069), (15, 0.7428), (16, 0.8463), (17, 0.8857), (18, 0.9629), (19, 0.9725)]),
    11: (2021, 'Monza', [(1, 0.1573), (2, 0.1672), (3, 0.2564), (4, 0.3686), (5, 0.3776), (6, 0.44), (7, 0.4954), (8, 0.681), (9, 0.6968), (10, 0.7145), (11, 0.9031)]),
    12: (2023, 'Singapore', [(1, 0.082), (2, 0.0961), (3, 0.1105), (4, 0.1415), (5, 0.1964), (6, 0.2837), (7, 0.3605), (8, 0.4074), (9, 0.4461), (10, 0.5323), (11, 0.5654), (12, 0.582), (13, 0.6162), (14, 0.7315), (15, 0.7768), (16, 0.8771), (17, 0.8925), (18, 0.9468), (19, 0.9709)]),
    13: (2025, 'Suzuka', [(1, 0.1216), (2, 0.142), (3, 0.1846), (4, 0.2073), (5, 0.2339), (6, 0.2623), (7, 0.3196), (8, 0.3911), (9, 0.418), (10, 0.4727), (11, 0.4994), (12, 0.543), (13, 0.653), (14, 0.6798), (15, 0.8597), (16, 0.9278), (17, 0.9403), (18, 0.969)]),
    14: (2021, 'Yas Marina Circuit', [(1, 0.0743), (2, 0.1206), (3, 0.1605), (4, 0.1974), (5, 0.2723), (6, 0.5017), (7, 0.5131), (8, 0.5516), (9, 0.7079), (10, 0.7723), (11, 0.8029), (12, 0.8278), (13, 0.8486), (14, 0.8719), (15, 0.923), (16, 0.9672)]),
    15: (2021, 'Austin', [(1, 0.1183), (2, 0.163), (3, 0.2114), (4, 0.2273), (5, 0.2455), (6, 0.2698), (7, 0.312), (8, 0.3403), (9, 0.3574), (10, 0.396), (11, 0.4664), (12, 0.6856), (13, 0.7287), (14, 0.742), (15, 0.7792), (16, 0.8137), (17, 0.8384), (18, 0.8638), (19, 0.9156), (20, 0.9719)]),
    16: (2023, 'Interlagos', [(1, 0.0816), (2, 0.1048), (3, 0.1487), (4, 0.3269), (5, 0.3653), (6, 0.4691), (7, 0.5016), (8, 0.5397), (9, 0.5695), (10, 0.6385), (11, 0.6878), (12, 0.7567), (13, 0.783), (14, 0.844), (15, 0.9386)]),
    17: (2022, 'Spielberg', [(1, 0.1003), (2, 0.2485), (3, 0.3184), (4, 0.5082), (5, 0.552), (6, 0.6285), (7, 0.7031), (8, 0.75), (9, 0.8748), (10, 0.9189)]),
    19: (2021, 'Mexico City', [(1, 0.2839), (2, 0.3011), (3, 0.3154), (4, 0.4791), (5, 0.4957), (6, 0.5277), (7, 0.6064), (8, 0.6332), (9, 0.6509), (10, 0.6947), (11, 0.7188), (12, 0.85), (13, 0.892), (14, 0.9074), (15, 0.9178), (16, 0.933), (17, 0.9616)]),
    20: (2022, 'Baku', [(1, 0.0495), (2, 0.1061), (3, 0.2502), (4, 0.2877), (5, 0.3438), (6, 0.3535), (7, 0.4182), (8, 0.4513), (9, 0.4556), (10, 0.4605), (11, 0.4684), (12, 0.478), (13, 0.5452), (14, 0.5831), (15, 0.6203), (16, 0.6803), (17, 0.712), (18, 0.7518), (19, 0.7776), (20, 0.8298)]),
    26: (2021, 'Zandvoort', [(1, 0.0855), (2, 0.158), (3, 0.197), (4, 0.2475), (5, 0.2914), (6, 0.3293), (7, 0.4006), (8, 0.4759), (9, 0.5274), (10, 0.5886), (11, 0.7266), (12, 0.7473), (13, 0.8195), (14, 0.8858)]),
    27: (2022, 'Imola', [(1, 0.0522), (2, 0.1817), (3, 0.1944), (4, 0.2234), (5, 0.312), (6, 0.3319), (7, 0.3889), (8, 0.4708), (9, 0.5216), (10, 0.5493), (11, 0.6007), (12, 0.6201), (13, 0.6371), (14, 0.7221), (15, 0.7321), (16, 0.8453), (17, 0.8853), (18, 0.9141), (19, 0.9777)]),
    29: (2022, 'Jeddah', [(1, 0.0793), (2, 0.089), (3, 0.1119), (4, 0.1614), (5, 0.1787), (6, 0.2037), (7, 0.2228), (8, 0.235), (9, 0.2605), (10, 0.2773), (11, 0.2938), (12, 0.3083), (13, 0.3946), (14, 0.4467), (15, 0.4802), (16, 0.5012), (17, 0.5177), (18, 0.5543), (19, 0.5866), (20, 0.6206), (21, 0.6534), (22, 0.6932), (23, 0.7078), (24, 0.7312), (25, 0.7787), (26, 0.838), (27, 0.9012)]),
    30: (2022, 'Miami', [(1, 0.0707), (2, 0.0902), (3, 0.1072), (4, 0.213), (5, 0.2388), (6, 0.2665), (7, 0.2923), (8, 0.3109), (9, 0.4091), (10, 0.4612), (11, 0.5806), (12, 0.6017), (13, 0.6259), (14, 0.6398), (15, 0.6434), (16, 0.6603), (17, 0.9064), (18, 0.9323), (19, 0.9712)]),
    31: (2023, 'Las Vegas', [(1, 0.0452), (2, 0.0607), (3, 0.0913), (4, 0.111), (5, 0.2501), (6, 0.2928), (7, 0.3284), (8, 0.337), (9, 0.3577), (10, 0.437), (11, 0.4799), (12, 0.5173), (13, 0.641), (14, 0.8322), (15, 0.842), (16, 0.8516), (17, 0.9738)]),
    32: (2023, 'Losail', [(1, 0.148), (2, 0.202), (3, 0.2434), (4, 0.3212), (5, 0.3503), (6, 0.4083), (7, 0.4818), (8, 0.5173), (9, 0.5398), (10, 0.5829), (11, 0.6408), (12, 0.6977), (13, 0.735), (14, 0.773), (15, 0.8277), (16, 0.9159)]),
}

VICINO_M = 100         # una curva ufficiale entro 100 m dall'apice è «quella»
MEDIANA_MAX_M = 60     # oltre, la tabella non torna con questa pista: numerazione nostra


def _posizioni(track_id, lunghezza):
    t = UFFICIALI.get(track_id)
    if not t or not lunghezza:
        return None
    return [(str(n), f * lunghezza) for n, f in t[2]]


def _velocita_a(c, d):
    """Velocità del giro c alla distanza d (il campione più vicino), o None."""
    if not c:
        return None
    best, v = 1e9, None
    for di, vi in zip(c["d"], c["v"]):
        if di is not None and vi is not None and abs(di - d) < best:
            best, v = abs(di - d), vi
    return v if best < 30 else None


def assegna(curve, track_id, lunghezza, giro=None):
    """Mette in ogni curva `nome` («2» o «13 e 14») e `numeri` ([«13», «14»]).
    `giro` (la traccia del riferimento, facoltativa): una seconda curva ufficiale vicina entra nel
    nome solo se lì si va ancora piano (entro 70 km/h dal minimo: una chicane, non l'uscita di un
    tornante). Restituisce "ufficiale" o "nostra" (e allora `nome` è il numero nostro)."""
    for cu in curve:
        cu["nome"] = str(cu["n"])
        cu["numeri"] = [str(cu["n"])]
    uff = _posizioni(track_id, lunghezza)
    if not uff or not curve:
        return "nostra"

    def costo(s):
        tot = 0.0
        for cu in curve:
            tot += min(150.0, min(abs(cu["apice"] - (p + s)) for _, p in uff))
        return tot + 0.2 * abs(s)

    s = min(range(-150, 151, 5), key=costo)
    nomi, distanze = [], []
    for cu in curve:
        vicini = sorted(((abs(cu["apice"] - (p + s)), n, p) for n, p in uff), key=lambda x: x[0])
        distanze.append(vicini[0][0])
        scelti = [vicini[0]]
        if len(vicini) > 1 and vicini[1][0] <= VICINO_M:
            v2 = _velocita_a(giro, vicini[1][2] + s)
            if giro is None or v2 is None or v2 - cu["vmin"] <= 70:
                scelti.append(vicini[1])
        scelti.sort(key=lambda v: v[2])          # in ordine sul giro
        nomi.append([v[1] for v in scelti])
    distanze.sort()
    mediana = distanze[len(distanze) // 2]
    usati = [n for ns in nomi for n in ns]
    if mediana > MEDIANA_MAX_M or len(usati) != len(set(usati)):
        return "nostra"
    for cu, ns in zip(curve, nomi):
        cu["numeri"] = ns
        cu["nome"] = " e ".join(ns)
    return "ufficiale"


def etichetta(cu, maiuscola=True, prep=""):
    """«Curva 2» oppure «Curve 13 e 14», come si dice alla radio; con prep="a", "da" o "la":
    «alla curva 2», «dalle curve 13 e 14», «la curva 2»."""
    nome = cu.get("nome") or str(cu["n"])
    piu = " e " in nome
    parola = "curve" if piu else "curva"
    art = {"a": ("alla", "alle"), "da": ("dalla", "dalle"), "la": ("la", "le")}.get(prep)
    testo = f"{art[piu]} {parola} {nome}" if art else f"{parola} {nome}"
    return testo[0].upper() + testo[1:] if maiuscola else testo
