"""Etapa 5 (v3) — persistência da pressão, tetos de swaps e ponte v2 → v3.

Motivação (auditoria da segunda rodada, 24/11/2026): na v2, cada trajetória emendava episódios históricos sem
pausa por 48 meses ("estresse permanente"). O modelo de regimes proposto pelo ChatGPT troca a ideia de que cada trajetório emenda
em episódioss sem pausa por 48 meses por uma cadeia de Markov sobre meses de alta depreciação, mas mistura nos meses 
"normais" as compras de reservas de 2006–2012 e os leilões do programa de swaps de 2013–2015 (ver 03_Codigo/auditoria/reproducao_gpt_revisao.py). Aqui a persistência
vira uma dimensão explícita, com unidades que a história observa: episódios inteiros de intervenção.

Regimes de persistência (todos começam com um episódio no mês 1, o choque da política):
  permanente          episódios emendados sem pausa (= v2; sorteio proporcional ao nº de blocos)
  episódio único      um episódio histórico (pesos iguais), depois calmaria até o fim do horizonte
  recorrente 0,25/ano depois de cada episódio, calmaria; novo episódio chega com taxa de 0,25 por ano
  recorrente 0,50/ano idem, com o dobro da frequência
Calmaria (padrão): demanda zero — o BC não vende nem compra. Variantes: + receitas de juros das reservas
(mediana do demonstrativo oficial) e meses históricos fora de episódios (2004–2026), que embutem as compras de
reservas do período de entrada de capitais (variante otimista, análoga ao modelo do ChatGPT).
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import CONFIG, FIGURAS, TABELAS, TRATADOS, log, salvar_json  # noqa: E402
from src.simulacao import (Blocos, anexar_blocos, entradas_linhas_abertas, resumir, simular,  # noqa: E402
                           sequencia_replay, sortear_episodios, sortear_sequencias)

P = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
SEED, N = P["simulacao"]["semente"], P["simulacao"]["n_trajetorias"]
HS = P["horizontes_meses"]["valores"]
H = max(HS)
PV3 = P["v3_persistencia"]
LAMS = PV3["lambdas"]


def taxa_para_hazard(eventos_por_ano: float) -> float:
    """Probabilidade mensal de chegada de um processo de Poisson com a taxa anual dada."""
    return 1 - math.exp(-eventos_por_ano / 12)


def carregar():
    comp = pd.read_csv(TABELAS / "etapa1_componentes_ara.csv")
    ref = comp.iloc[-1]
    r1 = json.loads((TABELAS / "etapa1_resumo.json").read_text(encoding="utf-8"))
    tetos = pd.read_csv(TABELAS / "etapa1_tetos_swap.csv")
    dref = pd.Timestamp(ref["data_referencia"])
    ag, ag2 = r1["agregado_monetario_principal"], r1["agregado_regra_v2"]
    pisos = {f"100% ARA ({ag.upper()})": float(ref["ara_recalculada_usd_bi"]),
             f"100% ARA ({ag2.upper()}, v2)": float(ref[f"ara_{ag2}_usd_bi"]),
             "Greenspan-Guidotti (v3)": float(ref["dcp_piso_gg_usd_bi"])}
    # linhas em aberto na data de referência: devolução no mês do vencimento contratual
    at = pd.read_csv(TRATADOS / "atuacoes_cambio.csv", parse_dates=["data", "data_liquidacao", "data_vencimento"])
    entradas, ab = entradas_linhas_abertas(at, ref["data_referencia"], H)
    dem = pd.read_csv(TRATADOS / "reservas_demonstrativo_mensal.csv", parse_dates=["data"])
    juros = float(dem["receitas_juros"].median())
    return {"data_ref": ref["data_referencia"], "R0": float(ref["reservas_usd_bi"]), "S0": float(r1["swap_em_aberto_usd_bi"]),
            "pisos": pisos, "piso_base": list(pisos)[0],
            "tetos": dict(zip(tetos.teto, tetos.valor_usd_bi.astype(float))), "teto_base": tetos.teto.iloc[0],
            "linhas_abertas": ab[["data", "volume_aceito_usd_bi", "data_vencimento", "mes"]].assign(
                data=lambda x: x.data.dt.date.astype(str), data_vencimento=lambda x: x.data_vencimento.dt.date.astype(str)).to_dict("records"),
            "entradas_linhas": entradas, "juros_mensal_mediana": juros,
            "juros_periodo": [str(dem.data.min().date()), str(dem.data.max().date())]}


def blocos_calma_historica(prazo_meses: int) -> pd.DataFrame:
    """Blocos de 20 dias úteis fora das janelas de episódio, 2004-01-01 a data de referência (mesma regra de 04_episodios)."""
    d = pd.read_csv(TABELAS / "etapa2_oferta_diaria_bc.csv", parse_dates=["data"]).set_index("data")
    ep = pd.read_csv(TABELAS / "etapa2_episodios.csv", parse_dates=["inicio", "fim"])
    d = d.loc["2004-01-01":ENT["data_ref"]]
    fora = np.ones(len(d), dtype=bool)
    for _, e in ep.iterrows():
        fora &= ~((d.index >= e.inicio) & (d.index <= e.fim))
    d = d[fora]
    # trechos contíguos (quebra quando há episódio entre dois dias)
    pos = np.flatnonzero(fora)
    quebra = np.r_[0, np.flatnonzero(np.diff(pos) > 1) + 1, len(pos)]
    linhas = []
    for a, z in zip(quebra[:-1], quebra[1:]):
        trecho = d.iloc[a:z]
        for k in range(0, len(trecho), 20):
            sub = trecho.iloc[k:k + 20]
            if len(sub) < 10:
                continue
            f = 20 / len(sub)
            linhas.append({"inicio": sub.index[0].date(), "fim": sub.index[-1].date(), "dias_uteis": len(sub),
                           "avista": f * sub["avista_liquido"].sum(), "temporario": f * (sub["linha_venda"].sum() + sub["outros_ida"].sum()),
                           "swap": f * sub["swap_var_estoque"].sum(), "prazo_meses": prazo_meses})
    return pd.DataFrame(linhas)


def registrar(linhas, base: dict, out: dict):
    for h in HS:
        for medida in ("T_F", "T_F_material", "T_R", "T_S"):
            linhas.append({**base, "horizonte_meses": h, "medida": medida, **resumir(out[medida], h)})


def rodar(idx, lam, piso, teto, subst, entradas):
    return simular(BB, idx, np.full(H, lam), ENT["R0"], piso, ENT["S0"], teto, subst, entradas=entradas,
                   limiar_material=PV3["limiar_material_usd_bi"])


def seq(persist: str, rng_off: int, calma, pesos="iguais"):
    rng = np.random.default_rng(SEED + rng_off)
    if persist == "permanente":
        return sortear_sequencias(B0, N, H, rng)
    return sortear_episodios(BB, N, H, rng, HAZ[persist], calma, pesos=pesos)


def lambda_estrela(ep: int, piso: float, teto: float, subst: bool, entradas) -> float:
    """Maior λ (bisseção em [0, 10]) com o qual a reprodução do episódio não deixa demanda sem atender em 48 meses."""
    idx = sequencia_replay(BB, ep, H, IDX_ZERO)
    ok = lambda l: np.isinf(simular(BB, idx, np.full(H, l), ENT["R0"], piso, ENT["S0"], teto, subst, entradas=entradas)["T_F"][0])  # noqa: E731
    if ok(10.0):
        return float("inf")
    lo, hi = 0.0, 10.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


if __name__ == "__main__":
    t0 = time.time()
    ENT = carregar()
    bl = pd.read_csv(TABELAS / "episodios_blocos.csv")
    B0 = Blocos.de_tabela(bl)
    NOMES = bl[bl.status != "descartado (<10 dias)"].episodio.drop_duplicates().tolist()
    prazo_global = int(np.median(B0.prazo_meses))
    BB, z = anexar_blocos(B0, np.zeros(1), np.zeros(1), np.zeros(1), np.ones(1, dtype=int))
    IDX_ZERO = int(z[0])
    calm = blocos_calma_historica(prazo_global)
    BB, idx_calma_hist = anexar_blocos(BB, calm.avista.to_numpy(), calm.temporario.to_numpy(), calm.swap.to_numpy(),
                                       calm.prazo_meses.to_numpy())
    TX = PV3["taxas_episodios_por_ano"]
    HAZ = {"episódio único": 0.0, **{f"recorrente {t:.2f}/ano".replace(".", ","): taxa_para_hazard(t) for t in TX}}
    PISO, TETO = ENT["pisos"][ENT["piso_base"]], ENT["tetos"][ENT["teto_base"]]
    EL = ENT["entradas_linhas"]
    ZERO = np.array([IDX_ZERO])
    linhas = []

    # A) grade principal
    for k, persist in enumerate(["permanente", *HAZ]):
        idx = seq(persist, 0, ZERO)
        for lam in LAMS:
            for subst in (True, False):
                out = rodar(idx, lam, PISO, TETO, subst, EL)
                registrar(linhas, {"bloco": "A_principal", "persistencia": persist, "calmaria": "zero", "lambda": lam,
                                   "piso": ENT["piso_base"], "teto": ENT["teto_base"], "versao": "substituível" if subst else "não substituível",
                                   "pesos_episodios": "proporcional à duração" if persist == "permanente" else "iguais"}, out)
    # C) tetos de swaps
    tetos = {**ENT["tetos"], "sem teto (limite só nas reservas)": 1e9}
    for persist in ("permanente", "recorrente 0,25/ano"):
        idx = seq(persist, 0, ZERO)
        for nome_t, teto in tetos.items():
            for subst in (True, False):
                registrar(linhas, {"bloco": "C_tetos", "persistencia": persist, "calmaria": "zero", "lambda": 1.0, "piso": ENT["piso_base"],
                                   "teto": nome_t, "versao": "substituível" if subst else "não substituível"},
                          rodar(idx, 1.0, PISO, teto, subst, EL))
    # D) pisos
    for persist in ("permanente", "recorrente 0,25/ano"):
        idx = seq(persist, 0, ZERO)
        for nome_p, piso in ENT["pisos"].items():
            for subst in (True, False):
                registrar(linhas, {"bloco": "D_pisos", "persistencia": persist, "calmaria": "zero", "lambda": 1.0, "piso": nome_p,
                                   "teto": ENT["teto_base"], "versao": "substituível" if subst else "não substituível"},
                          rodar(idx, 1.0, piso, TETO, subst, EL))
    # E) calmaria
    for persist in ("recorrente 0,25/ano", "recorrente 0,50/ano"):
        for nome_c, calma, extra in [("zero", ZERO, 0.0), ("zero + juros das reservas", ZERO, ENT["juros_mensal_mediana"]),
                                     ("meses históricos fora de episódios (2004–2026)", idx_calma_hist, 0.0)]:
            idx = seq(persist, 0, calma)
            for subst in (True, False):
                registrar(linhas, {"bloco": "E_calmaria", "persistencia": persist, "calmaria": nome_c, "lambda": 1.0, "piso": ENT["piso_base"],
                                   "teto": ENT["teto_base"], "versao": "substituível" if subst else "não substituível"},
                          rodar(idx, 1.0, PISO, TETO, subst, EL + extra))
    # F) pesos dos episódios
    for persist in ("episódio único", "recorrente 0,25/ano"):
        idx = seq(persist, 0, ZERO, pesos="duracao")
        for subst in (True, False):
            registrar(linhas, {"bloco": "F_pesos", "persistencia": persist, "calmaria": "zero", "lambda": 1.0, "piso": ENT["piso_base"],
                               "teto": ENT["teto_base"], "versao": "substituível" if subst else "não substituível",
                               "pesos_episodios": "proporcional à duração"}, rodar(idx, 1.0, PISO, TETO, subst, EL))
    # G) ARA dinâmica (sensibilidade validada na etapa 1): a parcela da moeda cresce à mediana histórica do M3 e é
    # convertida pelo câmbio realizado em cada bloco; meses de calmaria com câmbio constante; demais componentes fixos.
    r1 = json.loads((TABELAS / "etapa1_resumo.json").read_text(encoding="utf-8"))
    g_m3, m0 = r1["ara_dinamica"]["g_m3_mediana_12m_2016_2026"], r1["ara_dinamica"]["contrib_moeda_ref_usd_bi"]
    cam = pd.read_csv(TRATADOS / "cambio_diario.csv", parse_dates=["data"]).set_index("data")["cambio_brl_usd"]
    def dlog(ini, fim):
        a, z = cam.loc[:pd.Timestamp(ini) - pd.Timedelta(days=1)], cam.loc[:pd.Timestamp(fim)]
        return float(np.log(z.iloc[-1] / a.iloc[-1])) if len(a) and len(z) else 0.0
    okb = bl[bl.status != "descartado (<10 dias)"]
    dl = np.array([dlog(r.inicio, r.fim) for r in okb.itertuples()] + [0.0] + [dlog(r.inicio, r.fim) for r in calm.itertuples()])
    def piso_dinamico(idx):
        fxrel = np.exp(np.cumsum(dl[idx], axis=1))
        meses = np.arange(1, H + 1)[None, :]
        return PISO - m0 + m0 * (1 + g_m3) ** (meses / 12) / fxrel
    piso48 = {}
    for persist in ("permanente", "recorrente 0,25/ano", "episódio único"):
        idx = seq(persist, 0, ZERO)
        bb = B0 if persist == "permanente" else BB
        pd_ = piso_dinamico(idx)
        piso48[persist] = {"mediana": float(np.median(pd_[:, -1])), "p10": float(np.percentile(pd_[:, -1], 10)), "p90": float(np.percentile(pd_[:, -1], 90)),
                           "mediana_mes12": float(np.median(pd_[:, 11]))}
        for subst in (True, False):
            o = simular(bb, idx, np.ones(H), ENT["R0"], pd_, ENT["S0"], TETO, subst, entradas=EL)
            registrar(linhas, {"bloco": "G_ara_dinamica", "persistencia": persist, "calmaria": "zero", "lambda": 1.0,
                               "piso": "100% ARA dinâmica (sensibilidade)", "teto": ENT["teto_base"],
                               "versao": "substituível" if subst else "não substituível"}, o)
    # H) robustez da lista de episódios (varredura sistemática: inclui nov/2020–mar/2021 e dez/2021–jan/2022)
    blr = pd.read_csv(TABELAS / "episodios_blocos_robustez.csv")
    Br = Blocos.de_tabela(blr)
    Brz, zr = anexar_blocos(Br, np.zeros(1), np.zeros(1), np.zeros(1), np.ones(1, dtype=int))
    for persist in ("permanente", "recorrente 0,25/ano", "episódio único"):
        rng = np.random.default_rng(SEED)
        if persist == "permanente":
            bb, idx = Br, sortear_sequencias(Br, N, H, rng)
        else:
            bb, idx = Brz, sortear_episodios(Brz, N, H, rng, HAZ[persist], np.array([int(zr[0])]))
        for subst in (True, False):
            registrar(linhas, {"bloco": "H_robustez_episodios", "persistencia": persist, "calmaria": "zero", "lambda": 1.0,
                               "piso": ENT["piso_base"], "teto": ENT["teto_base"], "versao": "substituível" if subst else "não substituível",
                               "pesos_episodios": f"{len(Br.n_ep)} episódios (lista + varredura)"},
                      simular(bb, idx, np.ones(H), ENT["R0"], PISO, ENT["S0"], TETO, subst, entradas=EL))
    # I) cenário (b) como fluxo, sob persistência (entrada no mês 12)
    conv = json.loads((TABELAS / "cenario_b_conversao_exportacoes.json").read_text(encoding="utf-8"))
    fluxo_b = conv["fluxo_mensal_medio_2021_2025_usd_bi"]
    for persist in ("permanente", "recorrente 0,25/ano"):
        idx = seq(persist, 0, ZERO)
        bb = B0 if persist == "permanente" else BB
        for f in P["cenario_b_exportadores"]["fracao_f"]:
            extra = np.zeros(H)
            extra[11:] = f * fluxo_b
            for subst in (True, False):
                registrar(linhas, {"bloco": "I_cenario_b_fluxo", "persistencia": persist, "calmaria": "zero", "lambda": 1.0,
                                   "piso": ENT["piso_base"], "teto": ENT["teto_base"], "versao": "substituível" if subst else "não substituível",
                                   "f": f, "mes_entrada": 12, "fluxo_mensal_usd_bi": f * fluxo_b},
                          simular(bb, idx, np.ones(H), ENT["R0"], PISO, ENT["S0"], TETO, subst, entradas=EL + extra))
    df = pd.DataFrame(linhas)
    df.to_csv(TABELAS / "etapa5_persistencia_resultados.csv", index=False)

    # B) reprodução episódio a episódio e λ*
    rep, lst = [], []
    for e, nome in enumerate(NOMES):
        idx = sequencia_replay(BB, e, H, IDX_ZERO)
        dem = {"avista": float(B0.avista[B0.inicio_ep[e]:B0.inicio_ep[e] + B0.n_ep[e]].sum()),
               "temporario_bruto": float(B0.temporario[B0.inicio_ep[e]:B0.inicio_ep[e] + B0.n_ep[e]].sum()),
               "swap": float(B0.swap[B0.inicio_ep[e]:B0.inicio_ep[e] + B0.n_ep[e]].sum())}
        for lam in LAMS:
            for subst in (True, False):
                o = simular(BB, idx, np.full(H, lam), ENT["R0"], PISO, ENT["S0"], TETO, subst, entradas=EL)
                rep.append({"episodio": nome, "meses_episodio": int(B0.n_ep[e]), "lambda": lam, "versao": "substituível" if subst else "não substituível",
                            "T_F": o["T_F"][0], "T_R": o["T_R"][0], "T_S": o["T_S"][0], "reservas_finais": float(o["R_final"][0]),
                            "swaps_finais": float(o["S_final"][0]), **{f"demanda_{k}_lam1_usd_bi": v for k, v in dem.items()}})
        for nome_t in (ENT["teto_base"], "pico escalado pelo PIB em US$", "pico +50% (hipótese sem âncora histórica)", "sem teto (limite só nas reservas)"):
            for subst in (True, False):
                lst.append({"episodio": nome, "teto": nome_t, "versao": "substituível" if subst else "não substituível",
                            "lambda_estrela": lambda_estrela(e, PISO, tetos[nome_t], subst, EL)})
    rep, lst = pd.DataFrame(rep), pd.DataFrame(lst)
    rep.to_csv(TABELAS / "etapa5_replay_episodios.csv", index=False)
    lst.to_csv(TABELAS / "etapa5_lambda_estrela.csv", index=False)

    # G) ponte v2 → v3 (λ=1, permanente, mediana de T_F e P(T_F<=12))
    ponte = []
    B_V2 = Blocos.de_tabela(bl[bl.episodio != "2018"])  # lista de episódios da v2 (sem 2018)
    idx_v2 = sortear_sequencias(B_V2, N, H, np.random.default_rng(SEED))
    idx_p = seq("permanente", 0, ZERO)
    passos = [("v2: episódios v2, piso M4 sem intercompanhia, sem devolução das linhas em aberto", ENT["pisos"][list(ENT["pisos"])[1]], np.zeros(H), "v2"),
              ("+ piso v3 (M3 + DCP com intercompanhia)", PISO, np.zeros(H), "v2"),
              ("+ devolução das linhas em aberto (US$ %.2f bi)" % EL.sum(), PISO, EL, "v2"),
              ("+ episódio de 2018 na lista (= permanente v3)", PISO, EL, "permanente"),
              ("+ persistência: recorrente 0,25/ano (calmaria zero)", PISO, EL, "recorrente 0,25/ano"),
              ("+ persistência: episódio único", PISO, EL, "episódio único")]
    for nome, piso, ent_v, persist in passos:
        bb, idx = {"v2": (B_V2, idx_v2), "permanente": (B0, idx_p)}.get(persist, (BB, None))
        if idx is None:
            idx = seq(persist, 0, ZERO)
        for subst in (True, False):
            o = simular(bb, idx, np.ones(H), ENT["R0"], piso, ENT["S0"], TETO, subst, entradas=ent_v)
            r12, r48 = resumir(o["T_F"], 12), resumir(o["T_F"], 48)
            ponte.append({"passo": nome, "versao": "substituível" if subst else "não substituível", "p_falha_12": r12["p_esgotar_ate_H"],
                          "p_falha_48": r48["p_esgotar_ate_H"], "mediana_incondicional_48": r48["mediana_incondicional"],
                          "mediana_entre_falhas_48": r48["mediana_entre_esgotadas"]})
    ponte = pd.DataFrame(ponte)
    ponte.to_csv(TABELAS / "etapa5_ponte_v2_v3.csv", index=False)

    # figura: P(T_F <= t) por regime de persistência, λ = 1
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, subst in zip(axs, (True, False)):
        for persist in ["permanente", *HAZ]:
            o = rodar(seq(persist, 0, ZERO), 1.0, PISO, TETO, subst, EL)
            meses = np.arange(0, H + 1)
            ax.step(meses, [np.mean(o["T_F"] <= mm) for mm in meses], where="post", label=persist)
        ax.set_title(f"{'substituível' if subst else 'não substituível'} — λ = 1")
        ax.set_xlabel("meses desde 30/06/2026")
        ax.grid(alpha=.3)
    axs[0].set_ylabel("prob. acumulada de 1ª demanda não atendida")
    axs[0].legend(fontsize=8)
    fig.suptitle(f"Persistência da pressão — piso {ENT['piso_base']}, teto de swaps = pico histórico")
    fig.text(0.01, 0.01, f"Simulação própria, N = {N}, semente {SEED}. Episódios históricos de intervenção do BCB (2002–2025) reproduzidos na ordem original.", fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(FIGURAS / "etapa5_persistencia.png", dpi=300)

    salvar_json({**{k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in ENT.items()}, "hazard_mensal": HAZ,
                 "n_blocos_calma_historica": int(len(calm)), "calma_historica_media_avista": float(calm.avista.mean()),
                 "calma_historica_media_swap": float(calm.swap.mean()), "calma_historica_compras_soma": float(-calm.avista.clip(upper=0).sum()),
                 "episodios": NOMES, "meses_por_episodio": B0.n_ep.tolist(), "prazo_global_meses": prazo_global,
                 "ara_dinamica_piso": piso48, "g_m3": g_m3, "fluxo_b_mensal": fluxo_b,
                 "episodios_robustez": blr[blr.status != "descartado (<10 dias)"].episodio.drop_duplicates().tolist(),
                 "segundos": round(time.time() - t0, 1)}, TABELAS / "etapa5_entradas.json")
    log(f"Etapa 5 concluída em {time.time() - t0:.1f}s")
    pd.set_option("display.width", 250)
    a = df[(df.bloco == "A_principal") & (df.medida == "T_F") & (df.horizonte_meses.isin([12, 48]))]
    print(a.pivot_table(index=["persistencia", "versao", "lambda"], columns="horizonte_meses",
                        values=["p_esgotar_ate_H", "mediana_incondicional"]).round(3).to_string())
    print(rep[rep["lambda"] == 1.0][["episodio", "meses_episodio", "versao", "T_F", "T_R", "T_S"]].to_string())
    print(lst.pivot_table(index="episodio", columns=["teto", "versao"], values="lambda_estrela").round(2).to_string())
    print(ponte.round(3).to_string())
