
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import CONFIG, TABELAS, TRATADOS, log, salvar_json  # noqa: E402
from src.simulacao import (Blocos, anexar_blocos, entradas_linhas_abertas, resumir, simular,  # noqa: E402
                           sortear_episodios, sortear_sequencias)

P = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
SEED = P["simulacao"]["semente"]
H = 48
B_REP, N_BOOT = 300, 2000
HAZ = {"episódio único": 0.0, "recorrente 0,25/ano": 1 - math.exp(-0.25 / 12)}


def carregar_base():
    comp = pd.read_csv(TABELAS / "etapa1_componentes_ara.csv")
    ref = comp.iloc[-1]
    r1 = json.loads((TABELAS / "etapa1_resumo.json").read_text(encoding="utf-8"))
    at = pd.read_csv(TRATADOS / "atuacoes_cambio.csv", parse_dates=["data", "data_liquidacao", "data_vencimento"])
    ent, _ = entradas_linhas_abertas(at, ref["data_referencia"], H)
    teto = float(pd.read_csv(TABELAS / "etapa1_tetos_swap.csv").valor_usd_bi.iloc[0])
    pib = pd.read_csv(TRATADOS / "pib_mensal_usd.csv", parse_dates=["data"]).set_index("data")["pib_12m_usd_bi"]
    dref = pd.Timestamp(ref["data_referencia"])
    return {"ref": ref, "R0": float(ref["reservas_usd_bi"]), "S0": float(r1["swap_em_aberto_usd_bi"]), "piso": float(ref["ara_recalculada_usd_bi"]),
            "piso_gg": float(ref["dcp_piso_gg_usd_bi"]), "teto": teto, "EL": ent, "fx0": float(ref["cambio_brl_usd"]),
            "pib12_usd": float(pib.asof(pd.Timestamp(dref.year, dref.month, 1)))}


def blocos_com_zero(bl):
    b = Blocos.de_tabela(bl)
    bz, z = anexar_blocos(b, np.zeros(1), np.zeros(1), np.zeros(1), np.ones(1, dtype=int))
    return b, bz, int(z[0])


def sequencias(persist, b, bz, z, n, rng):
    if persist == "permanente":
        return b, sortear_sequencias(b, n, H, rng)
    return bz, sortear_episodios(bz, n, H, rng, HAZ[persist], np.array([z]))


# ------------------------------------------------------------------ A) bootstrap por episódio
def bootstrap(bl, E):
    ok = bl[bl.status != "descartado (<10 dias)"]
    eps = ok.episodio.drop_duplicates().tolist()
    rng_b = np.random.default_rng(SEED + 77)
    linhas = []
    for rep in range(B_REP):
        pick = rng_b.choice(eps, size=len(eps), replace=True)
        partes = []
        for j, e in enumerate(pick):
            x = ok[ok.episodio == e].copy()
            x["episodio"] = f"{e}#{j}"
            partes.append(x)
        b, bz, z = blocos_com_zero(pd.concat(partes, ignore_index=True))
        for persist in ("permanente", *HAZ):
            bb, idx = sequencias(persist, b, bz, z, N_BOOT, np.random.default_rng(SEED + rep))
            for subst in (True, False):
                o = simular(bb, idx, np.ones(H), E["R0"], E["piso"], E["S0"], E["teto"], subst, entradas=E["EL"])
                r12, r48 = resumir(o["T_F"], 12), resumir(o["T_F"], 48)
                linhas.append({"replica": rep, "persistencia": persist, "versao": "substituível" if subst else "não substituível",
                               "p12": r12["p_esgotar_ate_H"], "p48": r48["p_esgotar_ate_H"], "mediana": r48["mediana_incondicional"],
                               "tem_2013": "2013" in pick, "n_2013": int((pick == "2013").sum())})
    d = pd.DataFrame(linhas)
    d.to_csv(TABELAS / "etapa6_bootstrap_episodios_replicas.csv", index=False)
    res = []
    for (persist, versao), g in d.groupby(["persistencia", "versao"]):
        res.append({"persistencia": persist, "versao": versao, "replicas": len(g),
                    "p48_mediana": g.p48.median(), "p48_p05": g.p48.quantile(.05), "p48_p95": g.p48.quantile(.95),
                    "p12_mediana": g.p12.median(), "p12_p05": g.p12.quantile(.05), "p12_p95": g.p12.quantile(.95),
                    "p48_sem_2013": g[~g.tem_2013].p48.median(), "p48_com_2013": g[g.tem_2013].p48.median(),
                    "prop_replicas_sem_2013": float((~g.tem_2013).mean())})
    res = pd.DataFrame(res)
    res.to_csv(TABELAS / "etapa6_bootstrap_episodios.csv", index=False)
    return res


# ------------------------------------------------------------------ B) custo cambial dos swaps
def custo_swaps(bl, E):
    cam = pd.read_csv(TRATADOS / "cambio_diario.csv", parse_dates=["data"]).set_index("data")["cambio_brl_usd"]

    def dlog(ini, fim):
        a, z = cam.loc[:pd.Timestamp(ini) - pd.Timedelta(days=1)], cam.loc[:pd.Timestamp(fim)]
        return float(np.log(z.iloc[-1] / a.iloc[-1]))
    ok = bl[bl.status != "descartado (<10 dias)"]
    dl = np.array([dlog(r.inicio, r.fim) for r in ok.itertuples()] + [0.0])
    b, bz, z = blocos_com_zero(bl)
    pib_brl = E["pib12_usd"] * E["fx0"]  # aproximação: PIB de 12 meses em US$ x câmbio da data de referência
    economia_ano = 0.04 * pib_brl       # 'Eu Acuso': economia de cerca de 4% do PIB por ano (afirmação do autor)
    linhas = []
    for persist in ("permanente", *HAZ):
        bb, idx = sequencias(persist, b, bz, z, 10000, np.random.default_rng(SEED))
        fx = E["fx0"] * np.exp(np.cumsum(dl[idx], axis=1))
        fx_ant = np.concatenate([np.full((fx.shape[0], 1), E["fx0"]), fx[:, :-1]], axis=1)
        for subst in (True, False):
            o = simular(bb, idx, np.ones(H), E["R0"], E["piso"], E["S0"], E["teto"], subst, entradas=E["EL"], trajetorias=True)
            s_ant = np.concatenate([np.full((fx.shape[0], 1), E["S0"]), o["S_path"][:, :-1]], axis=1)
            custo = s_ant * (fx - fx_ant)  # R$ bi; positivo = perda do BC (paga a variação cambial)
            for hh in (12, 48):
                c = custo[:, :hh].sum(axis=1)
                linhas.append({"persistencia": persist, "versao": "substituível" if subst else "não substituível", "horizonte_meses": hh,
                               "custo_mediana_rs_bi": float(np.median(c)), "custo_p10_rs_bi": float(np.percentile(c, 10)),
                               "custo_p90_rs_bi": float(np.percentile(c, 90)),
                               "custo_mediana_pct_pib": float(100 * np.median(c) / pib_brl),
                               "custo_p90_pct_pib": float(100 * np.percentile(c, 90) / pib_brl),
                               "custo_p90_sobre_economia_alegada": float(np.percentile(c, 90) / (economia_ano * hh / 12)),
                               "deprec_mediana_pct": float(100 * (np.median(fx[:, hh - 1]) / E["fx0"] - 1))})
    d = pd.DataFrame(linhas)
    d.to_csv(TABELAS / "etapa6_custo_swaps.csv", index=False)
    return d, {"pib_rs_bi_aprox": pib_brl, "economia_alegada_rs_bi_ano": economia_ano}


# ------------------------------------------------------------------ C) referência externa (WPFXI)
# Grupo de comparação (hipótese de seleção, declarada): grandes emergentes com regime de metas de inflação e câmbio
# flutuante ou administrado de forma flexível. Exclui pegs, exportadores de petróleo com câmbio fixo e economias
# avançadas, cujos episódios (Líbia, Argélia, Arábia Saudita, Singapura, Suíça...) não são comparáveis ao Brasil.
EM_METAS = {"BRA": "Brasil", "CHL": "Chile", "COL": "Colômbia", "MEX": "México", "PER": "Peru", "CZE": "Rep. Tcheca",
            "HUN": "Hungria", "POL": "Polônia", "ROU": "Romênia", "TUR": "Turquia", "RUS": "Rússia", "ZAF": "África do Sul",
            "IND": "Índia", "IDN": "Indonésia", "KOR": "Coreia do Sul", "PHL": "Filipinas", "THA": "Tailândia", "ISR": "Israel"}


def episodios_externos(serie: pd.Series, limiar: float = 0.5, gap: int = 1) -> list[dict]:
    """Sequências de meses de venda líquida (valor < 0), juntando lacunas de até `gap` meses; tamanho = venda acumulada (% PIB)."""
    v = serie.sort_index()
    venda = (v < 0).to_numpy()
    eps, i, n = [], 0, len(v)
    while i < n:
        if not venda[i]:
            i += 1
            continue
        j, fim = i, i
        while j < n:
            if venda[j]:
                fim = j
                j += 1
            elif j + gap < n and venda[j + 1:j + 1 + gap].any():
                j += 1
            else:
                break
        tam = float(-v.iloc[i:fim + 1].sum())
        if tam >= limiar:
            eps.append({"inicio": v.index[i], "fim": v.index[fim], "meses": fim - i + 1, "venda_acumulada_pct_pib": tam,
                        "maior_mes_pct_pib": float(-v.iloc[i:fim + 1].min())})
        i = fim + 1
    return eps


def externo(E):
    d = pd.read_csv(TRATADOS / "fmi_wpfxi_mensal.csv", usecols=["COUNTRY", "INDICATOR", "TIME_PERIOD", "OBS_VALUE"])
    g = d[d.INDICATOR == "FXI_BROAD_PROXY_GDP"].copy()
    g["data"] = pd.to_datetime(g.TIME_PERIOD.str.replace("-M", "-") + "-01")
    linhas = []
    for pais, s in g.groupby("COUNTRY"):
        for e in episodios_externos(s.set_index("data").OBS_VALUE.astype(float)):
            linhas.append({"pais": pais, "emergente_metas": pais in EM_METAS, **e})
    ep = pd.DataFrame(linhas)
    ep.to_csv(TABELAS / "etapa6_episodios_externos.csv", index=False)
    cap = {"100% ARA (utilizável)": 100 * 61.28 / E["pib12_usd"],
           "só espaço em swaps": 100 * (E["teto"] - E["S0"]) / E["pib12_usd"],
           "Greenspan-Guidotti": 100 * ((E["R0"] - E["piso_gg"]) + (E["teto"] - E["S0"])) / E["pib12_usd"]}
    # capacidade 100% ARA a partir das tabelas (evita número digitado)
    capt = pd.read_csv(TABELAS / "etapa1_capacidade.csv")
    capt = capt[capt.data == capt.data.max()]
    cap["100% ARA (utilizável)"] = 100 * float(capt.iloc[0].folga_reservas_usd_bi + capt.iloc[0].espaco_swaps_usd_bi) / E["pib12_usd"]
    res = []
    for nome_g, sub in [("18 emergentes com metas de inflação", ep[ep.emergente_metas]), ("todos os países da base", ep)]:
        x = sub.venda_acumulada_pct_pib
        linha = {"grupo": nome_g, "n_episodios": int(len(sub)), "n_paises": int(sub.pais.nunique()),
                 "tamanho_p50": x.median(), "tamanho_p75": x.quantile(.75), "tamanho_p90": x.quantile(.9),
                 "meses_p50": sub.meses.median(), "meses_p75": sub.meses.quantile(.75), "meses_p90": sub.meses.quantile(.9)}
        for k, v in cap.items():
            linha[f"prop_acima_{k}"] = float((x > v).mean())
        res.append(linha)
    res = pd.DataFrame(res)
    res.to_csv(TABELAS / "etapa6_externo_resumo.csv", index=False)
    top = ep[ep.emergente_metas].sort_values("venda_acumulada_pct_pib", ascending=False).head(15)
    bra = ep[ep.pais == "BRA"]
    return res, top, bra, cap, {"grupo_emergentes": EM_METAS, "paises_do_grupo_na_base": sorted(set(ep[ep.emergente_metas].pais))}


if __name__ == "__main__":
    t0 = time.time()
    E = carregar_base()
    bl = pd.read_csv(TABELAS / "episodios_blocos.csv")
    boot = bootstrap(bl, E)
    cs, cs_meta = custo_swaps(bl, E)
    ext, top, bra, cap, ext_meta = externo(E)
    top.to_csv(TABELAS / "etapa6_externo_maiores.csv", index=False)
    bra.to_csv(TABELAS / "etapa6_externo_brasil.csv", index=False)
    salvar_json({"bootstrap": {"replicas": B_REP, "n_por_replica": N_BOOT}, "custo_swaps": cs_meta,
                 "capacidade_pct_pib": cap, "externo": ext_meta, "pib12_usd_bi": E["pib12_usd"], "fx0": E["fx0"],
                 "segundos": round(time.time() - t0, 1)}, TABELAS / "etapa6_entradas.json")
    pd.set_option("display.width", 250)
    print(boot.round(3).to_string()); print(cs.round(2).to_string()); print(cap); print(ext.round(3).T.to_string())
    print(top.to_string()); print(bra.to_string()); print(ext_meta)
    log(f"Etapa 6 concluída em {time.time() - t0:.0f}s")
