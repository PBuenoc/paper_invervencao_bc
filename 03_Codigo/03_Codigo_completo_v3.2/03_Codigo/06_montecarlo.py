
from __future__ import annotations

import json
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
from src.comum import CONFIG, FIGURAS, TABELAS, log, salvar_json  # noqa: E402
from src.simulacao import Blocos, entradas_linhas_abertas, resumir, simular, sortear_sequencias  # noqa: E402
from src.comum import TRATADOS  # noqa: E402

P = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
SEED = P["simulacao"]["semente"]
N = P["simulacao"]["n_trajetorias"]
HS = P["horizontes_meses"]["valores"]
HMAX = max(HS)


def entradas():
    comp = pd.read_csv(TABELAS / "etapa1_componentes_ara.csv")
    ref = comp.iloc[-1]
    res1 = json.loads((TABELAS / "etapa1_resumo.json").read_text(encoding="utf-8"))
    pisos = {f"{int(m * 100)}% ARA ({ref['agregado_principal'].upper()})": m * ref["ara_recalculada_usd_bi"]
             for m in P["pisos"]["ara_multiplos"]}
    pisos["Greenspan-Guidotti"] = ref["dcp_piso_gg_usd_bi"]
    ag2 = res1["agregado_regra_v2"]
    pisos[f"100% ARA ({ag2.upper()} sem intercompanhia, v2 — sensibilidade)"] = ref[f"ara_{ag2}_usd_bi"]
    at = pd.read_csv(TRATADOS / "atuacoes_cambio.csv", parse_dates=["data", "data_liquidacao", "data_vencimento"])
    ent, ab = entradas_linhas_abertas(at, ref["data_referencia"], HMAX)
    return {"data_ref": ref["data_referencia"], "R0": ref["reservas_usd_bi"], "S0": res1["swap_em_aberto_usd_bi"],
            "SMAX": res1["swap_max_usd_bi"], "pisos": pisos, "entradas_linhas": ent.tolist(),
            "linhas_abertas_total_usd_bi": float(ab.volume_aceito_usd_bi.sum())}


def rodar(b, ent, cenario: dict, lam_vec_fn, seed_offset=0, n=N, pi=0.0, k=0, aporte=None, horizontes=HS, entradas_extra=None):
    rng = np.random.default_rng(SEED + seed_offset)
    idx = sortear_sequencias(b, n, HMAX, rng, pi_corrida=pi, k_corrida=k)
    linhas = []
    for nome_piso, piso in ent["pisos"].items():
        for subst in (True, False):
            lam = lam_vec_fn()
            out = simular(b, idx, lam, ent["R0"], piso, ent["S0"], ent["SMAX"], subst,
                          aporte_mes=aporte[0] if aporte else None, aporte_valor=aporte[1] if aporte else 0.0,
                          entradas=np.array(ent["entradas_linhas"]) + (0 if entradas_extra is None else entradas_extra))
            for h in horizontes:
                for medida in ("T_R", "T_S", "T_C", "T_F"):
                    r = resumir(out[medida], h)
                    linhas.append({**cenario, "piso": nome_piso, "piso_usd_bi": piso, "versao": "substituível" if subst else "não substituível",
                                   "horizonte_meses": h, "medida": medida, **r})
    return linhas


if __name__ == "__main__":
    t0 = time.time()
    from src.comum import TABELAS as T
    bl = pd.read_csv(T / "episodios_blocos.csv")
    b = Blocos.de_tabela(bl)
    ent = entradas()
    rit = json.loads((T / "etapa2_ritmos.json").read_text(encoding="utf-8"))
    K = rit["k_meses_episodio_mais_longo"]
    linhas = []
    lambdas = [("alívio fiscal", l) for l in P["regimes_premio_risco"]["alivio_fiscal"]["lambda"]] + \
              [("perda de credibilidade", l) for l in P["regimes_premio_risco"]["perda_credibilidade"]["lambda"]]
    for regime, lam in lambdas:
        for pi in P["corrida"]["pi_mensal"]:
            cen = {"etapa": 3, "cenario": "base (regras atuais)" if pi == 0 else "corrida", "regime": regime, "lambda": lam,
                   "pi_corrida": pi, "k_corrida": K if pi > 0 else 0}
            linhas += rodar(b, ent, cen, lambda: np.full(HMAX, lam), pi=pi, k=K)
    df = pd.DataFrame(linhas)
    df.to_csv(TABELAS / "etapa3_montecarlo_resultados.csv", index=False)

    # checagem de convergência: N=5.000 vs N=10.000, cenário base λ=1, piso 100% ARA, T_C substituível, H=48
    conv = []
    for n in (P["simulacao"]["n_convergencia"], N):
        r = rodar(b, ent, {"n": n}, lambda: np.full(HMAX, 1.0), n=n, horizontes=[HMAX])
        sel = [x for x in r if x["piso"].startswith("100% ARA (M") and "sensib" not in x["piso"] and x["versao"] == "substituível" and x["medida"] == "T_C"][0]
        conv.append({"n": n, "p_esgotar_ate_48": sel["p_esgotar_ate_H"], "mediana_entre_esgotadas": sel["mediana_entre_esgotadas"],
                     "p10": sel["p10_entre_esgotadas"], "p90": sel["p90_entre_esgotadas"]})
    conv = pd.DataFrame(conv)
    conv.to_csv(TABELAS / "etapa3_convergencia.csv", index=False)

    # distribuição completa para a figura (base, λ ∈ grade, piso 100% ARA, T_C substituível)
    fig, ax = plt.subplots(figsize=(9, 5))
    p100 = [k for k in ent["pisos"] if k.startswith("100% ARA (M") and "sensib" not in k][0]
    for regime, lam in lambdas:
        rng = np.random.default_rng(SEED)
        idx = sortear_sequencias(b, N, HMAX, rng)
        out = simular(b, idx, np.full(HMAX, lam), ent["R0"], ent["pisos"][p100], ent["S0"], ent["SMAX"], True,
                      entradas=np.array(ent["entradas_linhas"]))
        t = out["T_C"]
        meses = np.arange(0, HMAX + 1)
        ax.step(meses, [np.mean(t <= m) for m in meses], where="post", label=f"λ = {lam} ({regime})")
    ax.set_xlabel("meses desde 30/06/2026")
    ax.set_ylabel("probabilidade acumulada de esgotar a capacidade")
    ax.set_title(f"Esgotamento da capacidade total (reservas acima de {p100} + espaço em swaps)\nversão substituível, regras atuais, sem corrida")
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    fig.text(0.01, 0.01, f"Simulação própria, N = {N}, semente {SEED}. Gasto mensal = λ × bloco histórico de 20 dias úteis (BCB, atuações 1999–2026).", fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIGURAS / "etapa3_prob_esgotamento.png", dpi=300)

    salvar_json({"entradas": ent, "k_corrida": K, "bloco_extremo": int(b.idx_extremo), "n_blocos": int(len(b.avista)),
                 "prazos_recompra_meses_por_bloco": sorted(set(b.prazo_meses.tolist())), "segundos": round(time.time() - t0, 1)},
                TABELAS / "etapa3_entradas.json")
    log(f"Etapa 3 concluída em {time.time() - t0:.1f}s; {len(df)} linhas.")
    base = df[(df.cenario == "base (regras atuais)") & (df.medida == "T_F")]
    pd.set_option("display.width", 250)
    print(base[base.piso == p100][["regime", "lambda", "versao", "horizonte_meses", "p_esgotar_ate_H", "mediana_entre_esgotadas",
                                    "p10_entre_esgotadas", "p90_entre_esgotadas", "mediana_incondicional"]].round(3).to_string())
    print(conv.to_string())
