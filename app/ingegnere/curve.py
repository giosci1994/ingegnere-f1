"""Curve, staccate e uscite: si trovano sul giro di riferimento e si misurano su ogni giro.

Le curve sono quelle del giro di riferimento (il migliore del giocatore): un minimo di
velocità preceduto, nei 400 m prima, da almeno 25 km/h in più. `n` è la nostra numerazione (in
ordine sul giro); il nome che si dice alla radio (`nome`, «2» o «13 e 14») è quello ufficiale
del circuito quando la pista è nella tabella di `numeri_curve.py`.

Per ogni curva e ogni giro:
  frenata   distanza in cui il freno supera 0,1 nei 400 m prima del minimo (None se non frena)
  vmin      velocità minima (km/h) tra 120 m prima e 120 m dopo
  gas       distanza in cui il gas torna sopra 0,9 dopo il minimo (entro 400 m)
  tempo     tempo nel tratto [inizio, fine] della curva di riferimento (interpolato sulla distanza)
  bloccaggio  slittamento anteriore sotto -0,2 (o posteriore sotto -0,25) in frenata, almeno 2 campioni
  pattina   slittamento posteriore sopra 0,2 in uscita, almeno 2 campioni
  veleggia  secondi senza gas né freno (gas < 0,1 e freno < 0,05) sopra i 100 km/h nel tratto
  rilascio  distanza in cui il freno torna sotto 0,1 dopo la frenata, prima del minimo
  sterzo_uscita  sterzo medio (valore assoluto) dal minimo a 150 m dopo

`causa()` dice che cosa è successo (per le tabelle); `consiglio()` dice come migliorare, con il
dato (per la radio e il riassunto).
"""

from bisect import bisect_left


def _validi(c):
    """Indici con distanza valida e crescente."""
    out, ultimo = [], -1e9
    for i, d in enumerate(c["d"]):
        if d is None or d < 0 or d < ultimo:
            continue
        out.append(i)
        ultimo = d
    return out


def _serie(c, campo, idx):
    return [c[campo][i] for i in idx]


def trova_curve(c):
    idx = _validi(c)
    if len(idx) < 50:
        return []
    d = _serie(c, "d", idx)
    v = _serie(c, "v", idx)
    curve = []
    i = 0
    n = len(d)
    while i < n:
        # minimo locale su ±60 m
        lo = bisect_left(d, d[i] - 60)
        hi = bisect_left(d, d[i] + 60)
        if v[i] == min(v[lo:hi + 1]) and v[i] < 330:
            prima = bisect_left(d, d[i] - 400)
            if max(v[prima:i + 1]) - v[i] >= 25:
                if not curve or d[i] - curve[-1]["apice"] > 150:
                    curve.append({"apice": d[i], "vmin": v[i]})
                elif v[i] < curve[-1]["vmin"]:
                    curve[-1] = {"apice": d[i], "vmin": v[i]}
                i = hi
                continue
        i += 1
    for k, cu in enumerate(curve, start=1):
        cu["n"] = k
        m = misura(c, cu, idx=idx)
        cu["frenata"] = m["frenata"]
        cu["gas"] = m["gas"]
        inizio = (m["frenata"] if m["frenata"] is not None else cu["apice"] - 250) - 120
        fine = (m["gas"] if m["gas"] is not None else cu["apice"] + 250) + 80
        cu["inizio"] = max(0.0, inizio)
        cu["fine"] = fine
    # i tratti non si sovrappongono: si taglia a metà strada
    for a, b in zip(curve, curve[1:]):
        if a["fine"] > b["inizio"]:
            mezzo = (a["apice"] + b["apice"]) / 2
            a["fine"] = min(a["fine"], mezzo)
            b["inizio"] = max(b["inizio"], mezzo)
    return curve


def tempo_a(c, distanza, idx=None):
    idx = idx if idx is not None else _validi(c)
    d = _serie(c, "d", idx)
    t = _serie(c, "t", idx)
    k = bisect_left(d, distanza)
    if k <= 0 or k >= len(d):
        return None
    d0, d1, t0, t1 = d[k - 1], d[k], t[k - 1], t[k]
    if d1 == d0:
        return t1
    return t0 + (t1 - t0) * (distanza - d0) / (d1 - d0)


def misura(c, cu, idx=None):
    idx = idx if idx is not None else _validi(c)
    d = _serie(c, "d", idx)
    ap = cu["apice"]
    a = bisect_left(d, ap - 400)
    m0 = bisect_left(d, ap - 120)
    m1 = bisect_left(d, ap + 120)
    b = bisect_left(d, ap + 400)
    sub = idx[m0:m1 + 1]
    if not sub:
        return {"frenata": None, "vmin": None, "gas": None, "tempo": None}
    vs = [c["v"][i] for i in sub]
    vmin = min(vs)
    imin = sub[vs.index(vmin)]
    frenata = None
    for i in idx[a:]:
        if i > imin:
            break
        if c["br"][i] is not None and c["br"][i] > 0.1:
            frenata = c["d"][i]
            break
    gas = None
    for i in idx[idx.index(imin):b + 1] if imin in idx else []:
        if c["th"][i] is not None and c["th"][i] > 0.9:
            gas = c["d"][i]
            break
    rilascio = None
    if frenata is not None:
        dentro = False
        for i in idx[a:]:
            if i > imin:
                break
            b_ = c["br"][i] or 0
            if b_ > 0.1:
                dentro = True
            elif dentro:
                rilascio = c["d"][i]
                break
    sterzi = []
    if c.get("st"):
        for i in idx[idx.index(imin):] if imin in idx else []:
            if c["d"][i] is None or c["d"][i] > c["d"][imin] + 150:
                break
            if c["st"][i] is not None:
                sterzi.append(abs(c["st"][i]))
    out = {"frenata": frenata, "vmin": vmin, "gas": gas, "rilascio": rilascio,
           "sterzo_uscita": round(sum(sterzi) / len(sterzi), 3) if sterzi else None}
    if "inizio" in cu:
        t0, t1 = tempo_a(c, cu["inizio"], idx), tempo_a(c, cu["fine"], idx)
        out["tempo"] = round(t1 - t0, 3) if t0 is not None and t1 is not None else None
        z0, z1 = bisect_left(d, cu["inizio"]), bisect_left(d, cu["fine"])
        zona = idx[z0:z1 + 1]
        def conta(cond):
            n, best = 0, 0
            for i in zona:
                n = n + 1 if cond(i) else 0
                best = max(best, n)
            return best
        sf = c.get("sf") or []
        sr = c.get("sr") or []
        sb = c.get("sb") or []
        out["bloccaggio"] = conta(lambda i: (c["br"][i] or 0) > 0.2 and (
            (sf and sf[i] is not None and sf[i] < -0.2) or (sb and sb[i] is not None and sb[i] < -0.25))) >= 2
        out["bloccaggio_dietro"] = conta(lambda i: (c["br"][i] or 0) > 0.2 and sb and sb[i] is not None and sb[i] < -0.25) >= 2
        out["pattina"] = conta(lambda i: (c["th"][i] or 0) > 0.5 and sr and sr[i] is not None and sr[i] > 0.2) >= 2
        vel = 0.0
        for j in range(1, len(zona)):
            i, p = zona[j], zona[j - 1]
            if (c["th"][i] or 0) < 0.1 and (c["br"][i] or 0) < 0.05 and (c["v"][i] or 0) > 100:
                vel += max(0.0, (c["t"][i] or 0) - (c["t"][p] or 0))
        out["veleggia"] = round(vel, 2)
    return out


def decimi(x):
    x = abs(x)
    if x < 0.15:
        return "un decimo"
    if x < 0.45:
        return f"{int(round(x * 10))} decimi"
    if x < 0.75:
        return "mezzo secondo"
    if x < 1.25:
        return "un secondo"
    return f"{round(x, 1)} secondi".replace(".", " virgola ")


def causa(m, r):
    """Il motivo principale per cui la curva è più lenta (m = misura del giro, r = riferimento).
    Restituisce (chiave, frase) o (None, None)."""
    if m.get("bloccaggio") and not r.get("bloccaggio"):
        return "bloccaggio", "bloccaggio in frenata"
    if m["frenata"] is not None and r["frenata"] is not None:
        diff = r["frenata"] - m["frenata"]          # positivo = ha frenato prima
        if diff >= 12:
            return "frenata_presto", f"hai frenato {int(round(diff))} metri prima"
        if diff <= -10 and m["vmin"] is not None and r["vmin"] is not None and m["vmin"] < r["vmin"] - 4:
            return "frenata_lunga", "frenata troppo lunga, sei arrivato lungo"
    if m["vmin"] is not None and r["vmin"] is not None and r["vmin"] - m["vmin"] >= 6:
        return "lento_centro", f"{int(round(r['vmin'] - m['vmin']))} chilometri orari più lento a centro curva"
    if m.get("pattina") and not r.get("pattina"):
        return "pattina", "pattinamento in uscita"
    if m["gas"] is not None and r["gas"] is not None and m["gas"] - r["gas"] >= 15:
        return "gas_tardi", f"gas pieno {int(round(m['gas'] - r['gas']))} metri dopo"
    if m.get("veleggia", 0) - r.get("veleggia", 0) >= 0.4:
        return "veleggia", "troppo tempo senza gas né freno"
    return None, None


def _metri(x):
    """Arrotondati a 5 m, come si dicono alla radio."""
    return max(5, int(5 * round(abs(x) / 5)))


def consiglio(m, r):
    """Come migliorare la curva (m = misura del giro, r = riferimento): (chiave, frase) o (None, None).
    Stesse cause di `causa()`, ma la frase dice che cosa fare, con il dato."""
    if m.get("bloccaggio") and not r.get("bloccaggio"):
        return "bloccaggio", "evita il bloccaggio: pesta meno forte all'inizio della frenata e rilascia piano"
    if m["frenata"] is not None and r["frenata"] is not None:
        diff = r["frenata"] - m["frenata"]          # positivo = ha frenato prima
        # oltre 80 m non è un punto di frenata da correggere (traffico, bandiere, un errore):
        # non si dice «frena 140 metri più tardi», si guarda il resto
        if 12 <= diff <= 80:
            return "frenata_presto", f"frena {_metri(diff)} metri più tardi"
        if -80 <= diff <= -10 and m["vmin"] is not None and r["vmin"] is not None and m["vmin"] < r["vmin"] - 4:
            return "frenata_lunga", f"frena {_metri(diff)} metri prima, così non arrivi lungo"
    if m["vmin"] is not None and r["vmin"] is not None and r["vmin"] - m["vmin"] >= 6:
        k = int(round(r["vmin"] - m["vmin"]))
        mr, rr = m.get("rilascio"), r.get("rilascio")
        if mr is not None and rr is not None and mr - rr >= 15:
            return "lento_centro", f"rilascia il freno {_metri(mr - rr)} metri prima e porta {k} chilometri orari in più a centro curva"
        return "lento_centro", f"rilascia il freno più dolcemente e porta {k} chilometri orari in più a centro curva"
    if m.get("pattina") and not r.get("pattina"):
        return "pattina", "dai gas più progressivo in uscita, pattini"
    if m["gas"] is not None and r["gas"] is not None and m["gas"] - r["gas"] >= 15:
        k = _metri(m["gas"] - r["gas"])
        su, sr_ = m.get("sterzo_uscita"), r.get("sterzo_uscita")
        if su is not None and sr_ is not None and su > sr_ * 1.15 and su - sr_ > 0.03:
            return "gas_tardi", f"meno sterzo in uscita: raddrizza prima e dai gas pieno {k} metri prima"
        return "gas_tardi", f"dai gas pieno {k} metri prima"
    if m.get("veleggia", 0) - r.get("veleggia", 0) >= 0.4:
        return "veleggia", "non restare senza gas né freno: passa prima dal freno al gas"
    return None, None


def confronta(c, rif, curve=None):
    """Confronto curva per curva di un giro con il riferimento."""
    curve = curve if curve is not None else trova_curve(rif)
    out = []
    for cu in curve:
        r = misura(rif, cu)
        m = misura(c, cu)
        delta = round(m["tempo"] - r["tempo"], 3) if m.get("tempo") is not None and r.get("tempo") is not None else None
        k, frase = causa(m, r)
        _, come = consiglio(m, r)
        out.append({"curva": cu["n"], "nome": cu.get("nome", str(cu["n"])), "apice": cu["apice"],
                    "delta": delta, "causa": k, "frase": frase, "consiglio": come,
                    "giro": m, "riferimento": r})
    return out
