from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import BRUTOS, RAIZ, TABELAS, TRATADOS, agora, log, registrar, salvar_json, sha256  # noqa: E402

PDF_ORIG = RAIZ.parents[1] / "01_Bibliografia" / "04_Documentos-Oficiais" / "FMI_2026_Brasil-ArtigoIV.pdf"  # só leitura
PDF_BRUTO = BRUTOS / "FMI_ArtigoIV_Brasil_2026_1BRAEA2026001.pdf"
MESES = {x: i + 1 for i, x in enumerate("Jan Fev Mar Abr Mai Jun Jul Ago Set Out Nov Dez".split())}


def sgs(codigo: int) -> pd.Series:
    f = sorted(BRUTOS.glob(f"BCB-SGS_{codigo}_*.json"))[-1]
    d = json.loads(f.read_text(encoding="utf-8"))
    a = pd.DataFrame([o for b in d["blocos"] for o in b["dados"]])
    a["data"] = pd.to_datetime(a["data"], dayfirst=True)
    a["valor"] = pd.to_numeric(a["valor"])
    return a.drop_duplicates("data").set_index("data")["valor"].sort_index()


def pdftotext() -> str:
    """Executável do pdftotext (poppler): PATH ou o que vem com o Git for Windows."""
    achado = shutil.which("pdftotext")
    if achado:
        return achado
    git = shutil.which("git")
    if git:
        cand = Path(git).resolve().parents[1] / "mingw64" / "bin" / "pdftotext.exe"
        if cand.exists():
            return str(cand)
    raise FileNotFoundError("pdftotext não encontrado (instale o poppler ou o Git for Windows)")


def fmi_art4() -> pd.DataFrame:
    if not PDF_BRUTO.exists():
        if not PDF_ORIG.exists():
            raise FileNotFoundError("PDF do Article IV não encontrado (nem em 01_brutos nem nos uploads)")
        shutil.copy2(PDF_ORIG, PDF_BRUTO)
    registrar(id_interno="fmi_artigo4_2026_pdf", nome_na_fonte="Brazil: 2026 Article IV Consultation — Staff Report (IMF Country Report)",
              fonte="FMI", url_ou_endpoint="01_Bibliografia/04_Documentos-Oficiais/FMI_2026_Brasil-ArtigoIV.pdf (IMF Country Report 1BRAEA2026001)", unidade="R$ bilhões (Tabela 4)",
              frequencia="anual", data_hora_acesso=agora(), arquivo_bruto=PDF_BRUTO.name, sha256=sha256(PDF_BRUTO),
              observacoes="Tabela 4 'Depository Corporations and Monetary Aggregates', p. 48 impressa (p. 54 do PDF).")
    txt = subprocess.run([pdftotext(), "-layout", str(PDF_BRUTO), "-"], capture_output=True, text=True, check=True).stdout
    paginas = txt.split("\f")
    for i, p in enumerate(paginas, start=1):
        if "Depository Corporations and Monetary Aggregates" in p and "Broad money (M2) 2/" in p:
            anos = [int(x) for x in re.findall(r"\b(20\d\d)\b", p.split("I. Central Bank")[0])][-5:]
            linha = [l for l in p.splitlines() if l.strip().startswith("Broad money (M2) 2/")][0]
            vals = [float(v.replace(",", "")) for v in re.findall(r"[\d,]+\.\d", linha.split("2/", 1)[1])]
            if len(vals) != len(anos):
                raise ValueError(f"anos {anos} e valores {vals} não casam")
            df = pd.DataFrame({"ano": anos, "moeda_ampla_fmi_brl_bi": vals, "pagina_pdf": i,
                               "fonte": "FMI, Article IV Brasil 2026, Tabela 4 (Broad money (M2))"})
            df.to_csv(TRATADOS / "fmi_moeda_ampla_art4.csv", index=False)
            log(f"FMI moeda ampla extraída da p. {i} do PDF: {dict(zip(anos, vals))}")
            return df
    raise ValueError("Tabela 4 não encontrada no PDF")


def estoques_oficiais() -> dict:
    of = pd.DataFrame({"swap_nocional_oficial_usd_bi": sgs(29723) / 1000, "linhas_oficial_usd_bi": sgs(29722) / 1000,
                       "swap_contratos_oficial": sgs(29724)})
    of.index.name = "data"
    of.to_csv(TRATADOS / "estoques_oficiais_diario.csv")
    rec = pd.read_csv(TRATADOS / "estoques_swap_linha_diario.csv", parse_dates=["data"]).set_index("data")
    j = of.join(rec[["swap_liquido_usd_bi", "linha_em_aberto_usd_bi"]], how="inner").dropna(subset=["swap_nocional_oficial_usd_bi", "swap_liquido_usd_bi"])
    j["dif_swap"] = j["swap_liquido_usd_bi"] - j["swap_nocional_oficial_usd_bi"]
    j["dif_linha"] = j["linha_em_aberto_usd_bi"] - j["linhas_oficial_usd_bi"]
    j.to_csv(TABELAS / "validacao_estoques_oficiais.csv")
    ref = pd.Timestamp("2026-06-30")
    out = {"dias_comparados": int(len(j)), "periodo": [str(j.index.min().date()), str(j.index.max().date())],
           "swap_erro_abs_medio_usd_bi": float(j["dif_swap"].abs().mean()),
           "swap_dias_com_dif_maior_0_01": int((j["dif_swap"].abs() > 0.01).sum()),
           "swap_dias_divergentes": {str(k.date()): round(float(v), 4) for k, v in j.loc[j["dif_swap"].abs() > 0.01, "dif_swap"].items()},
           "linha_erro_abs_medio_usd_bi": float(j["dif_linha"].abs().mean()),
           "linha_dias_com_dif_maior_0_01": int((j["dif_linha"].abs() > 0.01).sum()),
           "pico_oficial": {"data": str(of["swap_nocional_oficial_usd_bi"].idxmax().date()), "valor": float(of["swap_nocional_oficial_usd_bi"].max())},
           "ref_2026_06_30": {"swap_oficial": float(of["swap_nocional_oficial_usd_bi"].asof(ref)),
                              "swap_reconstruido": float(rec["swap_liquido_usd_bi"].asof(ref)),
                              "linha_oficial": float(of["linhas_oficial_usd_bi"].asof(ref)),
                              "linha_reconstruida": float(rec["linha_em_aberto_usd_bi"].asof(ref))},
           "ultimo_oficial": {"data": str(of.index.max().date()), "swap": float(of["swap_nocional_oficial_usd_bi"].iloc[-1]),
                              "linha": float(of["linhas_oficial_usd_bi"].iloc[-1])}}
    salvar_json(out, TABELAS / "validacao_estoques_oficiais.json")
    log(f"Validação estoques: {out['swap_erro_abs_medio_usd_bi']:.4f} (swap), {out['linha_erro_abs_medio_usd_bi']:.4f} (linha)")
    return out


def fluxos() -> pd.DataFrame:
    d = pd.DataFrame({"total_usd_bi": sgs(13961) / 1000, "comercial_usd_bi": sgs(13967) / 1000, "financeiro_usd_bi": sgs(13970) / 1000})
    d.index.name = "data"
    assert (d["comercial_usd_bi"] + d["financeiro_usd_bi"] - d["total_usd_bi"]).abs().max() < 1e-6, "identidade do fluxo violada"
    d.to_csv(TRATADOS / "fluxo_cambial_diario.csv")
    m = d.resample("MS").sum()
    m["dias_com_dado"] = d["total_usd_bi"].resample("MS").count()
    m.to_csv(TRATADOS / "fluxo_cambial_mensal.csv")
    return m


def pib_usd() -> pd.DataFrame:
    g = (sgs(4385) / 1000).rename("pib_mensal_usd_bi").to_frame()
    g["pib_12m_usd_bi"] = g["pib_mensal_usd_bi"].rolling(12).sum()
    g.index.name = "data"
    g.to_csv(TRATADOS / "pib_mensal_usd.csv")
    return g


def demonstrativo_reservas() -> pd.DataFrame:
    """Extrai a tabela 'Demonstrativo de variação das reservas' de cada arquivo do setor externo (vintage mais recente vence)."""
    itens = {"Variação total": "variacao_total", "Intervenções do Banco Central": "intervencoes_bcb",
             "Receitas de juros": "receitas_juros", "Saldo de linhas com recompra": "saldo_linhas", "Posição das reservas": "posicao_reservas"}
    regs = {}
    for f in sorted(BRUTOS.glob("BCB_tabelas-setor-externo_*.xlsx")):
        vintage = f.stem.split("_")[-1]
        x = pd.ExcelFile(f)
        ind = pd.read_excel(x, sheet_name=x.sheet_names[0] if "Índice" not in x.sheet_names else "Índice", header=None)
        alvo = ind[ind[1].astype(str).str.contains("Demonstrativo de variação das reservas", case=False, na=False)]
        if alvo.empty:
            log(f"AVISO {f.name}: demonstrativo não encontrado no índice")
            continue
        d = pd.read_excel(x, sheet_name=str(alvo.iloc[0, 0]), header=None)
        nomes = d[0].astype(str).str.strip()
        linhas = {k: nomes[nomes.str.fullmatch(k, case=False)].index.tolist() for k in itens}
        ano = None
        for col in range(1, d.shape[1]):
            y, mm = d.iloc[4, col], d.iloc[6, col]
            if pd.notna(y):
                try:
                    ano = int(y)
                except (TypeError, ValueError):
                    pass
            if not isinstance(mm, str) or mm.strip() not in MESES or ano is None:
                continue
            chave = pd.Timestamp(ano, MESES[mm.strip()], 1)
            try:
                valores = {itens[k]: float(d.iloc[ls[0], col]) / 1000 for k, ls in linhas.items() if ls}
            except (TypeError, ValueError):
                continue
            regs[chave] = {**valores, "vintage": vintage}  # arquivos em ordem crescente: o mais recente sobrescreve
    df = pd.DataFrame.from_dict(regs, orient="index").sort_index()
    df.index.name = "data"
    df.to_csv(TRATADOS / "reservas_demonstrativo_mensal.csv")
    log(f"Demonstrativo de reservas: {len(df)} meses, {df.index.min().date()} a {df.index.max().date()}")
    return df


def conversao_exportacoes() -> dict:
    """Parcela das exportações de bens que passa pelo mercado de câmbio: câmbio contratado de exportação (SGS 13962)
    sobre exportações de bens do balanço de pagamentos (SGS 22708), somadas por ano nos mesmos meses.
    Norma = razão agregada de 2009–2018. Excesso retido = (norma − razão) × exportações, quando positivo.
    É um teto para receita mantida fora: a diferença também inclui pagamentos feitos no exterior e descasamento de datas."""
    cx = (sgs(13962) / 1000).resample("MS").sum()
    f = sorted(BRUTOS.glob("BCB-SGS_22708_*.json"))[-1]
    d = json.loads(f.read_text(encoding="utf-8"))
    ex = pd.DataFrame([o for b in d["blocos"] for o in b["dados"]])
    ex["data"] = pd.to_datetime(ex["data"], dayfirst=True)
    ex = ex.set_index("data")["valor"].astype(float) / 1000
    m = pd.concat([cx.rename("cambio_exportacao_usd_bi"), ex.rename("exportacao_bens_bp_usd_bi")], axis=1, sort=True).dropna()
    m = m[m.index >= "2009-01-01"]
    a = m.groupby(m.index.year).agg(["sum", "count"])
    anual = pd.DataFrame({"cambio_exportacao_usd_bi": a[("cambio_exportacao_usd_bi", "sum")],
                          "exportacao_bens_bp_usd_bi": a[("exportacao_bens_bp_usd_bi", "sum")],
                          "meses": a[("exportacao_bens_bp_usd_bi", "count")]})
    anual["razao_conversao"] = anual["cambio_exportacao_usd_bi"] / anual["exportacao_bens_bp_usd_bi"]
    norma_df = anual.loc[2009:2018]
    norma = float(norma_df["cambio_exportacao_usd_bi"].sum() / norma_df["exportacao_bens_bp_usd_bi"].sum())
    anual["excesso_retido_usd_bi"] = ((norma - anual["razao_conversao"]).clip(lower=0) * anual["exportacao_bens_bp_usd_bi"])
    anual.index.name = "ano"
    anual.to_csv(TRATADOS / "exportacoes_conversao_cambio.csv")
    rec = anual.loc[2021:2025]
    out = {"norma_conversao_2009_2018": norma, "excesso_2021_2025_usd_bi": float(rec["excesso_retido_usd_bi"].sum()),
           "fluxo_mensal_medio_2021_2025_usd_bi": float(rec["excesso_retido_usd_bi"].sum() / rec["meses"].sum()),
           "recuo_observado_2024": {"excesso_2023": float(anual.loc[2023, "excesso_retido_usd_bi"]),
                                    "excesso_2024": float(anual.loc[2024, "excesso_retido_usd_bi"]),
                                    "fracao_revertida": float(1 - anual.loc[2024, "excesso_retido_usd_bi"] / anual.loc[2023, "excesso_retido_usd_bi"])},
           "fontes": "SGS 13962 (câmbio contratado, exportação, total) e SGS 22708 (exportações de bens, BP)"}
    salvar_json(out, TABELAS / "cenario_b_conversao_exportacoes.json")
    log(f"Conversão das exportações: norma {norma:.4f}; excesso 2021–2025 US$ {out['excesso_2021_2025_usd_bi']:.1f} bi")
    return out


WPFXI_INDICADORES = ["FXI_BROAD_PROXY_GDP", "FXI_BROAD_PROXY_USD", "FXI_BROAD_PUB_USD", "FXI_SPOT_PUB_USD"]


def wpfxi() -> dict:
    """WPFXI do FMI em formato longo. Aceita o CSV longo da API SDMX ou o CSV largo exportado do portal data.imf.org.

    No portal, SERIES_CODE = PAÍS.INDICADOR.FREQUÊNCIA (ex.: BRA.FXI_BROAD_PROXY_GDP.M); as colunas AAAA-Mmm são os meses.
    Mantém só frequência mensal e os 4 indicadores usados; células vazias são descartadas (não há preenchimento).
    """
    api = sorted(BRUTOS.glob("FMI_WPFXI_intervencao_cambial_mensal_*.csv"))
    portal = sorted(BRUTOS.glob("FMI-portal_WPFXI_*.csv"))
    if api:
        f = api[-1]
        d = pd.read_csv(f, usecols=["COUNTRY", "INDICATOR", "TIME_PERIOD", "OBS_VALUE"])
    elif portal:
        f = portal[-1]
        w = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
        cod = w.SERIES_CODE.str.split(".", expand=True)
        w = w.assign(COUNTRY=cod[0], INDICATOR=cod[1], FREQ=cod[2])
        w = w[(w.FREQ == "M") & w.INDICATOR.isin(WPFXI_INDICADORES)]
        meses = [c for c in w.columns if re.fullmatch(r"\d{4}-M\d{2}", c)]
        d = w.melt(id_vars=["COUNTRY", "INDICATOR"], value_vars=meses, var_name="TIME_PERIOD", value_name="OBS_VALUE")
    else:
        raise FileNotFoundError("WPFXI sem bruto em 01_brutos (rode 01d_download_fxi_fmi.py ou salve a exportação do portal)")
    d = d[d.INDICATOR.isin(WPFXI_INDICADORES)].dropna(subset=["OBS_VALUE"])
    d = d.assign(OBS_VALUE=d.OBS_VALUE.astype(float), arquivo_bruto=f.name, tipo="dado")
    d = d.sort_values(["COUNTRY", "INDICATOR", "TIME_PERIOD"]).reset_index(drop=True)
    d.to_csv(TRATADOS / "fmi_wpfxi_mensal.csv", index=False)
    out = {"arquivo_bruto": f.name, "n_observacoes": int(len(d)), "n_paises": int(d.COUNTRY.nunique()),
           "periodo": [d.TIME_PERIOD.min(), d.TIME_PERIOD.max()], "por_indicador": d.INDICATOR.value_counts().to_dict()}
    log(f"WPFXI: {out['n_observacoes']} obs., {out['n_paises']} países, {out['periodo'][0]} a {out['periodo'][1]} ({f.name})")
    return out


if __name__ == "__main__":
    resumo = {}
    for nome, fn in [("fmi_art4", fmi_art4), ("estoques_oficiais", estoques_oficiais), ("fluxos", fluxos),
                     ("pib_usd", pib_usd), ("demonstrativo_reservas", demonstrativo_reservas),
                     ("conversao_exportacoes", conversao_exportacoes), ("wpfxi", wpfxi)]:
        try:
            r = fn()
            resumo[nome] = "ok" if not isinstance(r, dict) else r
        except Exception as e:  # noqa: BLE001
            log(f"PENDENCIA {nome}: {e}")
            resumo[nome] = f"PENDENCIA: {e}"
    print(json.dumps(resumo, ensure_ascii=False, indent=1, default=str)[:3000])
