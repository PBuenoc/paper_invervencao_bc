"""Auditoria — reprodução do modelo de regimes da "segunda rodada" (ChatGPT, revisao.py) e diagnósticos.

Transcrição fiel da lógica de revisao.py (construção da base mensal 2004–2026, regimes pelo percentil 80
da depreciação mensal, cadeia de Markov, função sim), rodando sobre as MESMAS bases tratadas deste projeto.
Objetivo: (1) confirmar que os números do ChatGPT saem do código; (2) decompor a mudança de 9 para 37 meses.

Diagnósticos acrescentados (não estão no original):
  D1  meses "normais" com operações zeradas (sem compras de reservas, sem redução de swaps, sem linhas);
  D2  só a parte de compras à vista dos meses normais zerada;
  D3  substituição 0 e 1 no modo markov (para mostrar que sub=0,5 equivale a sub=0 na medida de primeira falha).

Uso (a partir da raiz do projeto): python 03_Codigo/auditoria/reproducao_gpt_revisao.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "03_Codigo"))
from src.simulacao import Blocos, simular, sortear_sequencias  # noqa: E402

T = RAIZ / "04_Resultados" / "tabelas"
D = RAIZ / "02_Dados" / "02_tratados"
OUT = RAIZ / "04_Resultados" / "auditoria_gpt"
OUT.mkdir(parents=True, exist_ok=True)
N, H, SEED = 10000, 48, 20261123
R0, S0, CAP, FLOOR = 367.558, 93.25, 114.918, 336.5503787164058  # valores do relatório v2 (como no original)


def summarize(t):
    return [round(100 * float(np.mean(t <= h)), 1) for h in (12, 24, 48)] + \
           [int(np.median(t)) if np.mean(t <= 48) > .5 else ">48"]


# ---------- base mensal (idêntica ao original) ----------
at = pd.read_csv(D / "atuacoes_cambio.csv", parse_dates=["data", "data_liquidacao", "data_vencimento"])
fx = pd.read_csv(D / "cambio_diario.csv", parse_dates=["data"]).set_index("data").cambio_brl_usd.resample("MS").last()
st = pd.read_csv(D / "estoques_swap_linha_diario.csv", parse_dates=["data"]).set_index("data").swap_liquido_usd_bi.resample("MS").last()
idxm = pd.date_range("2004-01-01", "2026-09-01", freq="MS")
m = pd.DataFrame(index=idxm)
m["fx"] = fx
m["dep"] = 100 * np.log(fx).diff()
m["sw"] = st.diff()
a = at[at.instrumento.isin(["Venda a Vista", "Compra a Vista", "Compra a Termo"])].copy()
a["signed"] = a.volume_aceito_usd_bi * np.where(a.instrumento == "Venda a Vista", 1, -1)
m["spot"] = a.groupby(a.data_liquidacao.dt.to_period("M").dt.to_timestamp()).signed.sum().reindex(idxm, fill_value=0)
ln = at[at.instrumento.isin(["Venda com Recompra", "Empréstimo", "Operação Compromissada"])].dropna(
    subset=["data_liquidacao", "data_vencimento"]).copy()
ln["month"] = ln.data_liquidacao.dt.to_period("M").dt.to_timestamp()
ln["lag"] = ((ln.data_vencimento.dt.year - ln.data_liquidacao.dt.year) * 12 + ln.data_vencimento.dt.month
             - ln.data_liquidacao.dt.month).clip(lower=0, upper=36)
tab = ln.pivot_table(index="month", columns="lag", values="volume_aceito_usd_bi", aggfunc="sum", fill_value=0).reindex(
    index=idxm, columns=range(37), fill_value=0).fillna(0)
m["temp"] = tab.sum(axis=1)
q = m.dep.quantile(.8)
reg = (m.dep >= q).astype(int).values
trans = pd.crosstab(reg[:-1], reg[1:], normalize="index").values
medias = m.groupby(reg)[["dep", "spot", "temp", "sw"]].mean()

rng = np.random.default_rng(SEED)
u = rng.random((N, H))
v = rng.random((N, H))
pools = [np.flatnonzero(reg == i) for i in (0, 1)]


def paths(mode):
    state = np.ones(N, dtype=int)
    ix = np.empty((N, H), int)
    for t in range(H):
        if mode == "normal":
            state[:] = 0
        if mode == "stress":
            state[:] = 1
        ix[:, t] = np.where(state == 1, pools[1][(v[:, t] * len(pools[1])).astype(int)],
                            pools[0][(v[:, t] * len(pools[0])).astype(int)])
        if mode == "markov":
            state = (u[:, t] < trans[state, 1]).astype(int)
    return ix


existing = np.zeros(H)
existing[0], existing[2], existing[4] = 2.05, 1, 1
spot0, sw0, line0 = m.spot.to_numpy(), m.sw.to_numpy(), tab.to_numpy()


def sim(mode="markov", lam=1, sub=.5, ceiling=CAP, piso=FLOOR, zerar_normais=False, zerar_compras_normais=False):
    spot, sw, line = spot0.copy(), sw0.copy(), line0.copy()
    if zerar_normais:  # D1
        spot[reg == 0], sw[reg == 0], line[reg == 0] = 0, 0, 0
    if zerar_compras_normais:  # D2
        spot[(reg == 0) & (spot < 0)] = 0
    ix = paths(mode)
    R = np.full(N, R0)
    S = np.full(N, S0)
    ret = np.zeros((N, H + 37))
    tt = np.full(N, np.inf)
    tr = np.full(N, np.inf)
    compras = np.zeros(N)
    for t in range(H):
        ii = ix[:, t]
        R += ret[:, t] + existing[t]
        F = piso
        aa, s, L = spot[ii] * lam, sw[ii] * lam, line[ii] * lam
        R += np.maximum(-aa, 0)
        compras += np.maximum(-aa, 0)
        S += np.minimum(s, 0)
        aa, s = np.maximum(aa, 0), np.maximum(s, 0)
        L = L.copy()
        L[:, 0] = 0
        d = L.sum(axis=1)
        exe = np.minimum(d, np.maximum(R - F, 0))
        ratio = np.divide(exe, d, out=np.zeros(N), where=d > 0)
        R -= exe
        ret[:, t + 1:t + 37] += L[:, 1:] * ratio[:, None]
        lackL = d - exe
        er = np.minimum(aa, np.maximum(R - F, 0))
        es = np.minimum(s, np.maximum(ceiling - S, 0))
        R -= er
        S += es
        lr, ls = aa - er, s - es
        exs = np.minimum(sub * lr, np.maximum(ceiling - S, 0))
        exr = np.minimum(sub * ls, np.maximum(R - F, 0))
        S += exs
        R -= exr
        fail = lackL + lr - exs + ls - exr > 1e-6
        tt[fail & np.isinf(tt)] = t + 1
        tr[(R <= F + 1e-6) & np.isinf(tr)] = t + 1
    return summarize(tt), summarize(tr), float(np.mean(compras))


if __name__ == "__main__":
    out = {"amostra_meses": int(len(m)), "limiar_p80_dep": float(q), "matriz_transicao": trans.round(4).tolist(),
           "medias_por_regime": medias.round(4).to_dict()}
    # meses normais que mais repõem reservas: quanto das compras vem de 2006–2012
    norm = m[reg == 0]
    compras_norm = (-norm.spot.clip(upper=0))
    out["compras_normais_total_usd_bi"] = round(float(compras_norm.sum()), 2)
    out["compras_normais_2006_2012_pct"] = round(100 * float(compras_norm["2006":"2012"].sum() / compras_norm.sum()), 1)
    # LOO com o simulador original (permanente), como no original
    bdf = pd.read_csv(T / "episodios_blocos.csv")
    loo = {}
    for e in ["nenhum", *bdf.episodio.unique()]:
        b = Blocos.de_tabela(bdf[bdf.episodio != e])
        idx = sortear_sequencias(b, N, H, np.random.default_rng(SEED))
        loo[e] = summarize(simular(b, idx, np.ones(H), R0, FLOOR, S0, CAP, True)["T_F"])
    out["loo"] = loo
    res = {}
    for mode in ("stress", "markov", "normal"):
        res[f"{mode}_lam1_sub0.5"] = sim(mode)
    res["markov_sub0"] = sim(sub=0)
    res["markov_sub1"] = sim(sub=1)
    res["markov_D1_normais_zerados"] = sim(zerar_normais=True)
    res["markov_D2_sem_compras_normais"] = sim(zerar_compras_normais=True)
    res["markov_D1_sub1"] = sim(sub=1, zerar_normais=True)
    out["simulacoes"] = {k: {"primeira_falha": v[0], "reservas_no_piso": v[1], "compras_medias_48m_usd_bi": round(v[2], 2)}
                         for k, v in res.items()}
    (OUT / "reproducao_revisao.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
