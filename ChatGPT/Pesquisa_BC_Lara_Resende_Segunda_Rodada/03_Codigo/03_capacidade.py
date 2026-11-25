"""Etapa 1 — Mapa da capacidade de intervenção (CLAUDE.md, seção 6.1)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import CONFIG, FIGURAS, TABELAS, TRATADOS, log, salvar_json  # noqa: E402

P = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
W = P["ara"]["pesos_flutuante"]

res = pd.read_csv(TRATADOS / "reservas_diarias.csv", parse_dates=["data"]).set_index("data")["reservas_usd_bi"]
cam = pd.read_csv(TRATADOS / "cambio_diario.csv", parse_dates=["data"]).set_index("data")["cambio_brl_usd"]
moeda = pd.read_csv(TRATADOS / "m2_mensal.csv", parse_dates=["data"]).set_index("data")
AGREGADOS = ["m2", "m3", "m4"]
exp = pd.read_csv(TRATADOS / "exportacoes_mensal.csv", parse_dates=["data"]).set_index("data")
div = pd.read_csv(TRATADOS / "divida_externa_prazo_original.csv")
pii = pd.read_csv(TRATADOS / "pii_passivos.csv")
cron = pd.read_csv(TRATADOS / "divida_externa_cronograma_mensal.csv", parse_dates=["ref"])
lp = pd.read_csv(TRATADOS / "divida_externa_lp_proximos12m_formato_antigo.csv", parse_dates=["ref"])
fmi = pd.read_csv(TRATADOS / "fmi_razao_reservas_ara.csv")
est = pd.read_csv(TRATADOS / "estoques_swap_linha_diario.csv", parse_dates=["data"]).set_index("data")


def ate(serie: pd.Series, data: pd.Timestamp):
    s = serie.loc[:data].dropna()
    return (s.index[-1], float(s.iloc[-1])) if len(s) else (None, float("nan"))


def ultimo_vintage(df, filtro):
    sub = df[filtro].sort_values("vintage")
    return sub[sub["vintage"] == sub["vintage"].max()] if len(sub) else sub


def divida_cp(ano, mes):
    sub = ultimo_vintage(div, (div.ano == ano) & (div.mes == mes))
    if sub.empty:
        return None
    cp = sub[sub.prazo == "curto prazo"]
    total = float(sub[(sub.setor == "total") & (sub.prazo == "curto prazo") & (sub.item == "total")]["valor_usd_mi"].iloc[0])
    excl = 0.0  # itens de curto prazo que o cronograma mensal exclui (rodapé 2 da tabela de cronograma)
    for _, r in cp.iterrows():
        it = str(r["item"])
        if (r["setor"] == "Bancos" and it.startswith("Empréstimos")) or it.startswith("Crédito comercial") or it.startswith("Moeda e dep"):
            excl += float(r["valor_usd_mi"])
    return {"cp_original": total, "cp_fora_do_cronograma": excl, "vintage": sub["vintage"].iloc[0],
            "estimado": bool(sub["estimado"].iloc[0])}


def lp_12m_exato(ref):
    sub = lp[(lp.ref == ref)].sort_values("vintage")
    if sub.empty:
        return None
    r = sub.iloc[-1]
    if not (ref.month == 12):
        return None  # só em referência de dezembro a coluna do ano seguinte cobre 12 meses
    return {"lp_12m": float(r["lp_imediato"] + r["lp_prox_ano"]), "lp_imediato": float(r["lp_imediato"]),
            "lp_prox_ano": float(r["lp_prox_ano"]), "vintage": r["vintage"], "ref_inferida": bool(r.get("ref_inferida", False))}


def principal_12m(ref):
    sub = cron[cron.ref == ref]
    if sub.empty:
        return None
    sub = sub[sub.vintage == sub.vintage.max()].copy()
    sub["data"] = pd.to_datetime(dict(year=sub.ano, month=sub.mes, day=1)) + pd.offsets.MonthEnd(0)
    janela = sub[(sub.data > ref) & (sub.data <= ref + pd.DateOffset(months=12))]
    if len(janela) != 12:
        log(f"AVISO cronograma {ref.date()}: {len(janela)} meses na janela (esperado 12)")
    return {"principal_12m_sem_intercomp": float(janela[["principal_gg", "principal_bancos", "principal_outros"]].sum().sum()),
            "principal_12m_intercomp": float(janela["principal_intercomp"].sum()), "n_meses": len(janela),
            "vintage": sub.vintage.iloc[0]}


def componentes(ref: pd.Timestamp) -> dict:
    d = {"data_referencia": ref.date().isoformat()}
    d["reservas_data"], d["reservas_usd_bi"] = ate(res, ref)
    d["cambio_data"], d["cambio_brl_usd"] = ate(cam, ref)
    mref = pd.Timestamp(ref.year, ref.month, 1)
    for ag in AGREGADOS:
        d[f"{ag}_brl_bi"] = float(moeda[f"{ag}_brl_bi"].get(mref, float("nan")))
        d[f"{ag}_usd_bi"] = d[f"{ag}_brl_bi"] / d["cambio_brl_usd"]
    d["export_12m_usd_bi"] = float(exp["export_12m_usd_bi"].get(mref, float("nan")))
    d["export_12m_soma_bens_servicos_usd_bi"] = float(exp.loc[:mref, "soma_bens_mais_servicos"].tail(12).sum())
    cp = divida_cp(ref.year, ref.month)
    d.update({f"divida_{k}": v for k, v in (cp or {}).items()})
    ex = lp_12m_exato(ref)
    ap = principal_12m(ref)
    d["lp_12m_exato_usd_mi"] = ex["lp_12m"] if ex else float("nan")
    d["lp_12m_exato_ref_inferida"] = ex["ref_inferida"] if ex else None
    if ap and cp:
        d["lp_12m_aprox_usd_mi"] = ap["principal_12m_sem_intercomp"] - (cp["cp_original"] - cp["cp_fora_do_cronograma"])
        d["principal_12m_intercomp_usd_mi"] = ap["principal_12m_intercomp"]
    else:
        d["lp_12m_aprox_usd_mi"] = float("nan")
    lp12 = d["lp_12m_exato_usd_mi"] if ex else d["lp_12m_aprox_usd_mi"]
    d["metodo_dcp"] = "exato (cronograma anual, formato antigo)" if ex else "aproximado (cronograma mensal)"
    d["dcp_residual_usd_bi"] = (cp["cp_original"] + lp12) / 1000 if cp else float("nan")
    pv = ultimo_vintage(pii, (pii.ano == ref.year) & (pii.mes == ref.month))
    get = lambda it: float(pv[pv.item == it]["valor_usd_mi"].iloc[0]) / 1000 if (pv.item == it).any() else float("nan")  # noqa: E731
    d["pil_usd_bi"], d["oil_usd_bi"] = get("pil"), get("oil")
    d["pii_vintage"] = pv["vintage"].iloc[0] if len(pv) else ""
    d["outros_passivos_usd_bi"] = d["pil_usd_bi"] + d["oil_usd_bi"] - d["dcp_residual_usd_bi"]
    d["contrib_exportacoes"] = W["exportacoes"] * d["export_12m_usd_bi"]
    d["contrib_dcp"] = W["dcp"] * d["dcp_residual_usd_bi"]
    d["contrib_outros_passivos"] = W["outros_passivos"] * d["outros_passivos_usd_bi"]
    base = d["contrib_exportacoes"] + d["contrib_dcp"] + d["contrib_outros_passivos"]
    ic = d.get("principal_12m_intercomp_usd_mi", float("nan")) / 1000
    for ag in AGREGADOS:
        d[f"contrib_moeda_{ag}"] = W["moeda_ampla"] * d[f"{ag}_usd_bi"]
        d[f"ara_{ag}_usd_bi"] = base + d[f"contrib_moeda_{ag}"]
        d[f"razao_{ag}"] = d["reservas_usd_bi"] / d[f"ara_{ag}_usd_bi"]
        # sensibilidades
        d[f"razao_{ag}_sens_ol_so_carteira"] = d["reservas_usd_bi"] / (d[f"ara_{ag}_usd_bi"] - d["contrib_outros_passivos"] + W["outros_passivos"] * d["pil_usd_bi"])
        d[f"razao_{ag}_sens_dcp_com_intercomp"] = d["reservas_usd_bi"] / (d[f"ara_{ag}_usd_bi"] + (W["dcp"] - W["outros_passivos"]) * ic)
    f = fmi[fmi.ano == ref.year]
    if ref.month == 12 and len(f):
        d["razao_fmi"] = float(f["razao_reservas_ara_fmi"].iloc[0])
        d["razao_fmi_estimativa"] = bool(f["estimativa_fmi"].iloc[0])
        d["ara_implicita_fmi_usd_bi"] = d["reservas_usd_bi"] / d["razao_fmi"]
        for ag in AGREGADOS:
            d[f"dif_razao_{ag}_pp"] = 100 * (d[f"razao_{ag}"] - d["razao_fmi"])
    for k in ("reservas_data", "cambio_data"):
        d[k] = d[k].date().isoformat() if d[k] is not None else ""
    return d


if __name__ == "__main__":
    refs = [pd.Timestamp(f"{a}-12-31") for a in range(2018, 2026)] + [pd.Timestamp("2026-06-30")]
    comp = pd.DataFrame([componentes(r) for r in refs])
    # agregado principal = o que melhor reproduz a razão publicada pelo FMI (menor erro absoluto médio)
    cmp_ = comp[comp.razao_fmi.notna() & comp[f"razao_m2"].notna()]
    erros = {ag: float(cmp_[f"dif_razao_{ag}_pp"].abs().mean()) for ag in AGREGADOS}
    AG = min(erros, key=erros.get)
    comp["agregado_principal"] = AG
    comp["ara_recalculada_usd_bi"] = comp[f"ara_{AG}_usd_bi"]
    comp["razao_recalculada"] = comp[f"razao_{AG}"]
    comp["dif_razao_pp"] = comp.get(f"dif_razao_{AG}_pp")
    comp.to_csv(TABELAS / "etapa1_componentes_ara.csv", index=False)
    erros_df = pd.DataFrame([{"agregado": ag, "erro_abs_medio_pp": e, "anos_comparados": ", ".join(cmp_.data_referencia.str[:4]),
                              "escolhido": ag == AG} for ag, e in erros.items()])
    erros_df.to_csv(TABELAS / "etapa1_escolha_agregado_monetario.csv", index=False)
    print(erros_df.to_string())

    # validação da aproximação do DCP contra o valor exato (anos em que existem os dois)
    val = comp[comp.lp_12m_exato_usd_mi.notna() & comp.lp_12m_aprox_usd_mi.notna()][
        ["data_referencia", "lp_12m_exato_usd_mi", "lp_12m_aprox_usd_mi", "lp_12m_exato_ref_inferida"]].copy()
    val["dif_usd_mi"] = val.lp_12m_aprox_usd_mi - val.lp_12m_exato_usd_mi
    val["dif_pct"] = 100 * val.dif_usd_mi / val.lp_12m_exato_usd_mi
    val.to_csv(TABELAS / "etapa1_validacao_aproximacao_dcp.csv", index=False)

    # série anual completa do FMI (implícita) para a figura e para comparação
    serie_fmi = []
    for _, r in fmi.iterrows():
        dref = pd.Timestamp(f"{int(r.ano)}-12-31")
        dt_r, rv = ate(res, dref)
        serie_fmi.append({"ano": int(r.ano), "reservas_bcb_fim_ano_usd_bi": rv, "data_reservas": dt_r.date().isoformat() if dt_r is not None else "",
                          "razao_fmi": r.razao_reservas_ara_fmi, "estimativa_fmi": bool(r.estimativa_fmi),
                          "ara_implicita_fmi_usd_bi": rv / r.razao_reservas_ara_fmi,
                          "ano_completo": dt_r is not None and dt_r.year == int(r.ano) and dt_r.month == 12})
    serie_fmi = pd.DataFrame(serie_fmi)
    serie_fmi.to_csv(TABELAS / "etapa1_ara_implicita_fmi_anual.csv", index=False)

    # data de referência principal = último registro (2026-06-30)
    ref = comp.iloc[-1]
    dref = pd.Timestamp(ref["data_referencia"])
    R = ref["reservas_usd_bi"]
    s_t = float(est.loc[:dref, "swap_liquido_usd_bi"].iloc[-1])
    linha_t = float(est.loc[:dref, "linha_em_aberto_usd_bi"].iloc[-1])
    s_max = float(est["swap_liquido_usd_bi"].max())
    s_max_data = est["swap_liquido_usd_bi"].idxmax().date().isoformat()
    pisos = []
    for mult in P["pisos"]["ara_multiplos"]:
        pisos.append({"piso": f"{int(mult * 100)}% ARA (recalculada)", "valor_usd_bi": mult * ref["ara_recalculada_usd_bi"], "tipo": "calculado"})
    pisos.append({"piso": "Greenspan-Guidotti (DCP residual)", "valor_usd_bi": ref["dcp_residual_usd_bi"], "tipo": "calculado"})
    # comparação: FMI implícito em fim de 2025 (estimativa do FMI)
    r25 = comp[comp.data_referencia == "2025-12-31"].iloc[0]
    for mult in P["pisos"]["ara_multiplos"]:
        pisos.append({"piso": f"{int(mult * 100)}% ARA implícita FMI (fim 2025, comparação)", "valor_usd_bi": mult * r25["ara_implicita_fmi_usd_bi"],
                      "tipo": "calculado (estimativa FMI)"})
    pisos = pd.DataFrame(pisos)
    cap = []
    for _, p in pisos.iterrows():
        comparavel = "fim 2025" not in p["piso"]
        Rb = R if comparavel else r25["reservas_usd_bi"]
        sb = s_t if comparavel else float(est.loc[:pd.Timestamp("2025-12-31"), "swap_liquido_usd_bi"].iloc[-1])
        cap.append({"piso": p["piso"], "data": ref["data_referencia"] if comparavel else "2025-12-31",
                    "reservas_usd_bi": Rb, "piso_usd_bi": p["valor_usd_bi"], "folga_reservas_usd_bi": Rb - p["valor_usd_bi"],
                    "swap_em_aberto_usd_bi": sb, "swap_max_usd_bi": s_max, "espaco_swaps_usd_bi": s_max - sb,
                    "capacidade_total_usd_bi": (Rb - p["valor_usd_bi"]) + (s_max - sb)})
    cap = pd.DataFrame(cap)
    pisos.to_csv(TABELAS / "etapa1_pisos.csv", index=False)
    cap.to_csv(TABELAS / "etapa1_capacidade.csv", index=False)
    resumo = {"data_referencia": ref["data_referencia"], "reservas_usd_bi": R, "reservas_data": ref["reservas_data"],
              "swap_em_aberto_usd_bi": s_t, "linha_em_aberto_usd_bi": linha_t, "swap_max_usd_bi": s_max, "swap_max_data": s_max_data,
              "ultima_reserva": {"data": res.index[-1].date().isoformat(), "valor_usd_bi": float(res.iloc[-1])},
              "agregado_monetario_principal": AG, "erro_abs_medio_pp_por_agregado": erros,
              "ultimo_swap": {"data": est.index[-1].date().isoformat(), "valor_usd_bi": float(est["swap_liquido_usd_bi"].iloc[-1])}}
    salvar_json(resumo, TABELAS / "etapa1_resumo.json")

    # figura: reservas x ARA implícita FMI (anual) e recalculada
    fig, ax = plt.subplots(figsize=(10, 5.5))
    sf = serie_fmi[serie_fmi.ano_completo].dropna()  # só anos com reserva de dezembro
    ax.plot(sf.ano, sf.reservas_bcb_fim_ano_usd_bi, "-o", color="#1f3a5f", label="Reservas (BCB, fim de ano)")
    obs, estm = sf[~sf.estimativa_fmi], sf[sf.estimativa_fmi]
    ax.plot(obs.ano, obs.ara_implicita_fmi_usd_bi, "-", color="#c0392b", label="100% ARA implícita no FMI")
    ax.plot(estm.ano, estm.ara_implicita_fmi_usd_bi, "--", color="#c0392b", label="100% ARA implícita no FMI (estimativa do FMI)")
    cr = comp[comp.data_referencia.str.endswith("12-31")]
    ax.plot(pd.to_datetime(cr.data_referencia).dt.year, cr.ara_recalculada_usd_bi, "s", color="#e67e22", label="100% ARA recalculada (BCB)")
    ax.set_ylabel("US$ bilhões")
    ax.set_title("Reservas internacionais e métrica ARA do FMI — Brasil, fim de ano")
    ax.legend(fontsize=8)
    ax.grid(alpha=.3)
    fig.text(0.01, 0.01, "Fontes: BCB (SGS 13621; tabelas do setor externo), FMI DataMapper (estimativas após 2021). Acesso: 23/11/2026.", fontsize=7)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIGURAS / "etapa1_reservas_vs_ara.png", dpi=300)
    log("Etapa 1 concluída.")
    print(comp[["data_referencia", "reservas_usd_bi", "ara_recalculada_usd_bi", "razao_recalculada", "razao_fmi", "dif_razao_pp", "metodo_dcp"]].to_string())
    print(val.to_string())
    print(cap.to_string())
    print(json.dumps(resumo, indent=1))
