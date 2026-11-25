"""Limpeza: transforma os brutos em bases tratadas (02_Dados/02_tratados/).

Não preenche lacunas. Unidades monetárias padronizadas em US$ bilhões, salvo indicação.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import xlrd

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import BRUTOS, TRATADOS, log  # noqa: E402

MESES = {"Jan": 1, "Fev": 2, "Mar": 3, "Abr": 4, "Mai": 5, "Jun": 6, "Jul": 7, "Ago": 8, "Set": 9,
         "Out": 10, "Nov": 11, "Dez": 12}


def ultimo(padrao: str) -> Path:
    arqs = sorted(glob.glob(str(BRUTOS / padrao)))
    if not arqs:
        raise FileNotFoundError(padrao)
    return Path(arqs[-1])


# ---------------------------------------------------------------- SGS
def sgs(codigo: int, nome: str, fator: float = 1.0) -> pd.DataFrame:
    arq = ultimo(f"BCB-SGS_{codigo}_*.json")
    j = json.loads(arq.read_text(encoding="utf-8"))
    obs = [o for b in j["blocos"] for o in b["dados"]]
    df = pd.DataFrame(obs)
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df[nome] = pd.to_numeric(df["valor"], errors="coerce") * fator
    df = df[["data", nome]].drop_duplicates("data").sort_values("data")
    n_na = df[nome].isna().sum()
    if n_na:
        log(f"AVISO SGS {codigo}: {n_na} valores não numéricos mantidos como NaN")
    return df


# ---------------------------------------------------------------- Tabelas do setor externo
def _num(c):
    return float(c) if isinstance(c, (int, float)) else np.nan


def achar_aba(wb, padrao: str):
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(min_row=1, max_row=6, values_only=True))
        t = " ".join(str(c) for r in rows for c in r if c).replace("\n", " ")
        if re.search(padrao, t, re.I):
            return ws, t
    return None, ""


def colunas_trimestrais(rows):
    """Acha linhas de ano e de mês no cabeçalho e devolve {indice_coluna: (ano, mes, estimado)}."""
    for i, r in enumerate(rows[:8]):
        if r and str(r[0]).strip().startswith("Discrimina"):
            anos = r
            # a linha de meses pode vir logo abaixo ou depois de uma linha vazia
            k = next(k for k in range(i + 1, i + 4)
                     if any(c and str(c).strip()[:3] in MESES for c in rows[k][1:]))
            meses = rows[k]
            i = k - 1
            cols, ano = {}, None
            for j in range(1, len(meses)):
                if j < len(anos) and isinstance(anos[j], (int, float)):
                    ano = int(anos[j])
                m = meses[j]
                if m and ano:
                    ms = str(m).strip()
                    mes = MESES.get(ms[:3])
                    if mes:
                        cols[j] = (ano, mes, "(e)" in ms)
            return cols, i + 2
    return {}, 0


def ler_divida_prazo_original(wb):
    ws, _ = achar_aba(wb, r"Dívida externa por devedor e prazo original")
    if ws is None:
        return []
    rows = list(ws.iter_rows(values_only=True))
    cols, ini = colunas_trimestrais(rows)
    setor, sub, saida = "total", None, []
    for r in rows[ini:]:
        if not r or r[0] is None:
            continue
        rot = str(r[0]).strip()
        if rot.startswith("Operações intercomp"):
            break  # só dívida externa bruta, sem intercompanhia
        if rot in ("Governo geral", "Banco Central", "Bancos", "Outros setores"):
            setor, sub = rot, None
            continue
        if rot.lower() in ("curto prazo", "longo prazo"):
            sub = rot.lower()
            item = "total"
        else:
            item = rot
        for j, (a, m, est) in cols.items():
            saida.append({"setor": setor if not rot.startswith("Dívida externa bruta") else "total",
                          "prazo": sub if not rot.startswith("Dívida externa bruta") else "total",
                          "item": "total" if rot.startswith("Dívida externa bruta") else item,
                          "ano": a, "mes": m, "estimado": est, "valor_usd_mi": _num(r[j])})
    return saida


def ler_pii_passivo(wb):
    ws, _ = achar_aba(wb, r"Posição de investimento internacional\s*Passivos|Posição de investimento internacional$")
    for w in wb.worksheets:
        rows = list(w.iter_rows(values_only=True))
        if any(r and str(r[0]).strip().startswith("Passivo (B)") for r in rows[:12]):
            ws = w
            break
    else:
        return []
    cols, ini = colunas_trimestrais(rows)
    alvo = {"Passivo (B)": "passivo_total", "Investimentos em carteira": "pil", "Outros investimentos": "oil"}
    saida, vistos = [], set()
    for r in rows[ini:]:
        if not r or r[0] is None:
            continue
        rot = str(r[0]).strip()
        for k, nome in alvo.items():
            if rot.startswith(k) and nome not in vistos:
                vistos.add(nome)
                for j, (a, m, est) in cols.items():
                    saida.append({"item": nome, "ano": a, "mes": m, "estimado": est, "valor_usd_mi": _num(r[j])})
    return saida


def ler_cronograma_mensal(wb):
    ws, titulo = achar_aba(wb, r"Cronograma mensal de pagamento")
    if ws is None:
        return None, []
    rows = list(ws.iter_rows(values_only=True))
    ref = None
    for r in rows[:6]:
        for c in r:
            if hasattr(c, "year"):
                ref = pd.Timestamp(c)
    # localizar colunas de Principal: Governo Geral, Bancos, Outros Setores, Intercompanhia
    hdr_i = next(i for i, r in enumerate(rows[:10]) if r and r[0] and str(r[0]).startswith("Mês"))
    nomes = rows[hdr_i]
    pos = {}
    for j, c in enumerate(nomes):
        if c and "Governo" in str(c):
            pos["gg"] = j
        elif c and "Bancos" in str(c):
            pos["bancos"] = j
        elif c and "Outros" in str(c):
            pos["outros"] = j
        elif c and "Opera" in str(c):
            pos["intercomp"] = j
    saida, ano = [], None
    for r in rows[hdr_i + 3:]:
        if not r or (r[0] is None and r[1] is None):
            continue
        if isinstance(r[0], (int, float)):
            ano = int(r[0])
        mes = MESES.get(str(r[1]).strip()[:3]) if r[1] else None
        if not (ano and mes):
            continue
        prev = bool(r[2]) and "(p)" in str(r[2])
        d = {"ano": ano, "mes": mes, "previsto": prev}
        for k, j in pos.items():
            d[f"principal_{k}"] = _num(r[j])
        saida.append(d)
    return ref, saida


def ler_cronograma_anual_lp(wb):
    """Formato antigo: tabela por setor do devedor com colunas Saldo | Imediato | ano1 | ano2 ..."""
    ws, titulo = achar_aba(wb, r"cronograma de amortização\s+Distribuição por setor do devedor")
    if ws is None:
        return None
    rows = list(ws.iter_rows(values_only=True))
    ref = next((pd.Timestamp(c) for r in rows[:6] for c in r if hasattr(c, "year")), None)
    hdr = next(r for r in rows[:8] if r and r[0] and str(r[0]).startswith("Discrimina"))
    j_imed = next((j for j, c in enumerate(hdr) if c and str(c).startswith("Imediato")), None)
    # 201904 não tem coluna "Imediato": o primeiro ano vem logo após "Saldo"
    j_prox = (j_imed + 1) if j_imed is not None else 2
    out = {"ref": ref, "ano_coluna_prox": hdr[j_prox]}
    for r in rows:
        if r and r[0] and str(r[0]).strip() in ("Curto Prazo", "Longo Prazo") and str(r[0]).strip() not in out:
            out[str(r[0]).strip()] = {"saldo": _num(r[1]),
                                      "imediato": _num(r[j_imed]) if j_imed is not None else 0.0,
                                      "prox_ano": _num(r[j_prox])}
    return out


def setor_externo():
    div, pii, cron, lp = [], [], [], []
    for f in sorted(glob.glob(str(BRUTOS / "BCB_tabelas-setor-externo_*.xlsx"))):
        vint = Path(f).stem.split("_")[-1]
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        for d in ler_divida_prazo_original(wb):
            d["vintage"] = vint
            div.append(d)
        for d in ler_pii_passivo(wb):
            d["vintage"] = vint
            pii.append(d)
        ref, rows = ler_cronograma_mensal(wb)
        for d in rows:
            d["vintage"], d["ref"] = vint, ref
            cron.append(d)
        a = ler_cronograma_anual_lp(wb)
        if a and "Longo Prazo" in a:
            ref_a, ref_inferida = a["ref"], False
            if ref_a is None:  # arquivos de 2019–2020 trazem a data como texto: regra observada nos demais
                ref_a = pd.Timestamp(f"{int(vint[:4]) - 1}-12-31") if vint[4:] == "04" else pd.Timestamp(f"{vint[:4]}-06-30")
                ref_inferida = True
            lp.append({"vintage": vint, "ref": ref_a, "ref_inferida": ref_inferida, "ano_prox": a["ano_coluna_prox"],
                       "lp_saldo": a["Longo Prazo"]["saldo"], "lp_imediato": a["Longo Prazo"]["imediato"],
                       "lp_prox_ano": a["Longo Prazo"]["prox_ano"],
                       "cp_saldo_nominal": a.get("Curto Prazo", {}).get("saldo")})
        log(f"setor externo {vint}: divida={len(div)} pii={len(pii)} cron={len(cron)} lp={len(lp)}")
    return pd.DataFrame(div), pd.DataFrame(pii), pd.DataFrame(cron), pd.DataFrame(lp)


# ---------------------------------------------------------------- Atuações
def atuacoes():
    arq = ultimo("BCB_historico-atuacoes-mercado-cambio_*.csv")
    a = pd.read_csv(arq, encoding="utf-8-sig", dtype=str)

    def num(s):
        return pd.to_numeric(s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")

    out = pd.DataFrame({
        "data": pd.to_datetime(a["Data"]),
        "data_liquidacao": pd.to_datetime(a["Data de Liquidação"], errors="coerce"),
        "data_vencimento": pd.to_datetime(a["Data de Vencimento"], errors="coerce"),
        "instrumento": a["Instrumento"].str.strip(),
        "modalidade": a["Modalidade"].str.strip(),
        "tipo_composto": a["Tipo Composto"].fillna("").str.strip(),
        "procedimento": a["Procedimento Operacional"].str.strip(),
        "volume_ofertado_usd_bi": num(a["Volume USD Ofertado"]) / 1e9,
        "volume_aceito_usd_bi": num(a["Volume USD Aceito"]) / 1e9,
    })
    return out

def estoque_em_aberto(df: pd.DataFrame, datas: pd.DatetimeIndex) -> pd.Series:
    """Soma dos volumes em aberto: entra na liquidação (inclusive), sai no vencimento (exclusive)."""
    ev = pd.concat([
        pd.Series(df["volume_aceito_usd_bi"].values, index=df["data_liquidacao"].values),
        pd.Series(-df["volume_aceito_usd_bi"].values, index=df["data_vencimento"].values),
    ]).groupby(level=0).sum().sort_index()
    acum = ev.cumsum()
    return acum.reindex(datas, method="ffill").fillna(0.0)

# ---------------------------------------------------------------- FMI
def fmi_ratio():
    out = []
    for suf in ("b",):
        arq = BRUTOS / f"IMF-DataMapper_ReservasAdequacao_export-20261123_{suf}.xls"
        sh = xlrd.open_workbook(str(arq), ignore_workbook_corruption=True, logfile=open(os.devnull, "w")).sheet_by_index(0)
        hdr = sh.row_values(0)
        est_apos = None
        for r in range(sh.nrows):
            v = sh.row_values(r)
            if v and v[0] == "Brazil":
                est_apos = int(v[-1]) if isinstance(v[-1], float) else None
                for i, h in enumerate(hdr):
                    if isinstance(h, float) and isinstance(v[i], float):
                        out.append({"ano": int(h), "razao_reservas_ara_fmi": v[i],
                                    "estimativa_fmi": est_apos is not None and int(h) > est_apos})
    return pd.DataFrame(out)


# ---------------------------------------------------------------- Copom, EMBI, Tesouro
def copom():
    j = json.loads(ultimo("BCB_historico-taxas-juros-copom_*.json").read_text(encoding="utf-8"))
    c = pd.DataFrame(j["conteudo"] if isinstance(j, dict) else j)
    c["data_reuniao"] = pd.to_datetime(c["DataReuniaoCopom"]).dt.tz_localize(None).dt.normalize()
    c["inicio_vigencia"] = pd.to_datetime(c["DataInicioVigencia"]).dt.tz_localize(None).dt.normalize()
    c = c.sort_values(["data_reuniao", "inicio_vigencia"])
    c["meta_anterior"] = c["MetaSelic"].shift(1)
    c["mudanca_pp"] = c["MetaSelic"] - c["meta_anterior"]
    return c[["NumeroReuniaoCopom", "ReuniaoExtraordinaria", "data_reuniao", "inicio_vigencia", "MetaSelic",
              "meta_anterior", "mudanca_pp"]].rename(columns={"NumeroReuniaoCopom": "reuniao", "MetaSelic": "meta_selic"})


def embi():
    j = json.loads(ultimo("IPEADATA_JPM366_EMBI366_2*.json").read_text(encoding="utf-8"))
    e = pd.DataFrame(j["value"])
    e["data"] = pd.to_datetime(e["VALDATA"].str[:10])
    return e[["data", "VALVALOR"]].rename(columns={"VALVALOR": "embi_pb"}).dropna()


def tesouro_lft():
    t = pd.read_csv(ultimo("TESOURO_estoque-dpf_*.csv"), sep=";", decimal=",", dtype={"Titulo/Contrato": str})
    t = t[(t["Classe da Carteira"] == "Mercado") & (t["Tipo de Divida"] == "Dívida Interna")]
    t["tipo"] = t["Titulo/Contrato"].str.extract(r"^([A-Z]+)")[0]
    t["mes"] = pd.to_datetime("01/" + t["Mes do Estoque"], format="%d/%m/%Y")
    g = t.groupby(["mes", "tipo"])["Valor do Estoque"].sum().unstack(fill_value=0)
    out = pd.DataFrame({"estoque_dpmfi_mercado_rs": g.sum(axis=1), "estoque_lft_rs": g.get("LFT", 0)})
    out["participacao_lft"] = out["estoque_lft_rs"] / out["estoque_dpmfi_mercado_rs"]
    return out.reset_index()


if __name__ == "__main__":
    res = sgs(13621, "reservas_usd_bi", 1 / 1000)
    cam = sgs(1, "cambio_brl_usd")
    selic = sgs(432, "meta_selic")
    exp_bs = sgs(22705, "export_bens_servicos_usd_bi", 1 / 1000)
    exp_b = sgs(22708, "export_bens_usd_bi", 1 / 1000)
    exp_s = sgs(22720, "export_servicos_usd_bi", 1 / 1000)
    m2 = sgs(27810, "m2_brl_bi", 1 / 1e6)  # R$ mil -> R$ bilhões
    m2 = m2.merge(sgs(27813, "m3_brl_bi", 1 / 1e6), on="data", how="outer").merge(sgs(27815, "m4_brl_bi", 1 / 1e6), on="data", how="outer")
    for df, n in ((res, "reservas_diarias"), (cam, "cambio_diario"), (selic, "meta_selic_diaria"), (m2, "m2_mensal")):
        df.to_csv(TRATADOS / f"{n}.csv", index=False)
    exp = exp_bs.merge(exp_b, on="data", how="outer").merge(exp_s, on="data", how="outer").sort_values("data")
    exp["soma_bens_mais_servicos"] = exp["export_bens_usd_bi"] + exp["export_servicos_usd_bi"]
    exp["export_12m_usd_bi"] = exp["export_bens_servicos_usd_bi"].rolling(12, min_periods=12).sum()
    exp.to_csv(TRATADOS / "exportacoes_mensal.csv", index=False)

    div, pii, cron, lp = setor_externo()
    div.to_csv(TRATADOS / "divida_externa_prazo_original.csv", index=False)
    pii.to_csv(TRATADOS / "pii_passivos.csv", index=False)
    cron.to_csv(TRATADOS / "divida_externa_cronograma_mensal.csv", index=False)
    lp.to_csv(TRATADOS / "divida_externa_lp_proximos12m_formato_antigo.csv", index=False)

    at = atuacoes()
    at.to_csv(TRATADOS / "atuacoes_cambio.csv", index=False)
    dias = pd.date_range("1999-01-01", at["data"].max(), freq="D")
    sw = at[at["instrumento"] == "Swap Cambial"]
    est = pd.DataFrame({"data": dias,
                        "swap_tradicional_usd_bi": estoque_em_aberto(sw[sw["modalidade"] == "Tradicional"], dias).values,
                        "swap_reverso_usd_bi": estoque_em_aberto(sw[sw["modalidade"] == "Reverso"], dias).values,
                        "linha_em_aberto_usd_bi": estoque_em_aberto(at[at["instrumento"] == "Venda com Recompra"], dias).values})
    est["swap_liquido_usd_bi"] = est["swap_tradicional_usd_bi"] - est["swap_reverso_usd_bi"]
    est.to_csv(TRATADOS / "estoques_swap_linha_diario.csv", index=False)

    fmi_ratio().to_csv(TRATADOS / "fmi_razao_reservas_ara.csv", index=False)
    copom().to_csv(TRATADOS / "copom_reunioes.csv", index=False)
    embi().to_csv(TRATADOS / "embi_diario.csv", index=False)
    tesouro_lft().to_csv(TRATADOS / "tesouro_participacao_lft.csv", index=False)
    log("Limpeza concluída.")
