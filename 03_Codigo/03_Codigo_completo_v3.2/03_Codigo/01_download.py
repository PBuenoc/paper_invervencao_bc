
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import BRUTOS, HOJE, agora, baixar, log, registrar, sha256  # noqa: E402

REFRESH = "--refresh" in sys.argv
FALHAS: list[dict] = []

SGS = {
    # codigo: (id_interno, nome confirmado no catálogo do BCB, unidade, frequência, início)
    13621: ("reservas_diarias", "Reservas internacionais - Conceito caixa - Total - diária", "US$ milhões", "diária", dt.date(1998, 9, 1)),
    1: ("cambio_venda_diario", "Taxa de câmbio - Livre - Dólar americano (venda) - diário", "R$/US$", "diária", dt.date(1999, 1, 1)),
    432: ("meta_selic", "Taxa de juros - Meta Selic definida pelo Copom", "% a.a.", "diária", dt.date(1999, 3, 5)),
    22705: ("export_bens_servicos_mensal", "Balança comercial e Serviços - mensal - receita", "US$ milhões", "mensal", dt.date(1995, 1, 1)),
    22708: ("export_bens_mensal", "Exportação de bens - Balanço de Pagamentos - mensal", "US$ milhões", "mensal", dt.date(1995, 1, 1)),
    22720: ("export_servicos_mensal", "Serviços - mensal - receita", "US$ milhões", "mensal", dt.date(1995, 1, 1)),
    27810: ("m2_mensal", "Meios de pagamento amplos - M2 (saldo em final de período) - Novo", "R$ mil", "mensal", dt.date(2001, 7, 1)),
    27813: ("m3_mensal", "Meios de pagamento amplos - M3 (saldo em final de período) - Novo", "R$ mil", "mensal", dt.date(2001, 7, 1)),
    27815: ("m4_mensal", "Meios de pagamento amplos - M4 (saldo em final de periodo) - Novo", "R$ mil", "mensal", dt.date(2001, 7, 1)),
}


def sgs(codigo: int) -> None:
    id_, nome, unid, freq, inicio = SGS[codigo]
    destino = BRUTOS / f"BCB-SGS_{codigo}_{id_}_{HOJE}.json"
    if destino.exists() and not REFRESH:
        log(f"CACHE {destino.name}")
    else:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
        blocos, ini, fim_total = [], inicio, dt.date.today()
        while ini <= fim_total:  # janelas de até 10 anos (limite da API)
            fim = min(dt.date(ini.year + 9, 12, 31), fim_total)
            tmp = BRUTOS / f".tmp_{codigo}_{ini.year}.json"
            baixar(url, tmp, params={"formato": "json", "dataInicial": ini.strftime("%d/%m/%Y"),
                                     "dataFinal": fim.strftime("%d/%m/%Y")}, refresh=True)
            dados = json.loads(tmp.read_text(encoding="utf-8"))
            tmp.unlink()
            blocos.append({"janela": [ini.isoformat(), fim.isoformat()], "dados": dados})
            ini = fim + dt.timedelta(days=1)
        destino.write_text(json.dumps({"codigo_sgs": codigo, "url": url, "blocos": blocos}, ensure_ascii=False), encoding="utf-8")
    conteudo = json.loads(destino.read_text(encoding="utf-8"))
    obs = [o for b in conteudo["blocos"] for o in b["dados"]]
    registrar(id_interno=id_, nome_na_fonte=nome, fonte="Banco Central do Brasil — SGS",
              url_ou_endpoint=f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados", codigo=str(codigo),
              unidade=unid, frequencia=freq, periodo_inicio=obs[0]["data"] if obs else "",
              periodo_fim=obs[-1]["data"] if obs else "", data_hora_acesso=agora(), arquivo_bruto=destino.name,
              sha256=sha256(destino), n_observacoes=str(len(obs)),
              observacoes="Nome, unidade e frequência conferidos no catálogo de dados abertos do BCB (campo codigo_sgs).")


def simples(id_, url, nome_arq, nome, fonte, unid, freq, obs="", params=None):
    destino = BRUTOS / nome_arq
    baixar(url, destino, params=params, refresh=REFRESH)
    registrar(id_interno=id_, nome_na_fonte=nome, fonte=fonte, url_ou_endpoint=url, unidade=unid,
              frequencia=freq, data_hora_acesso=agora(), arquivo_bruto=destino.name, sha256=sha256(destino),
              observacoes=obs)
    return destino


def tentar(func, *a, **k):
    try:
        return func(*a, **k)
    except Exception as e:  # noqa: BLE001
        log(f"PENDENCIA {a[0] if a else ''}: {e}")
        FALHAS.append({"item": str(a[0] if a else func.__name__), "erro": str(e)})
        return None


if __name__ == "__main__":
    for c in SGS:
        tentar(sgs, c)

    tentar(simples, "atuacoes_cambio",
           "https://www.bcb.gov.br/conteudo/dadosabertos/BCBDepin/historico-atuacoes-mercado-cambio.csv",
           f"BCB_historico-atuacoes-mercado-cambio_{HOJE}.csv",
           "Histórico de Atuações no Mercado de Câmbio", "Banco Central do Brasil — dados abertos (BCBDepin)",
           "US$ (Volume USD Aceito/Ofertado)", "por atuação",
           "Base desde jan/1999. Não registra cancelamentos nem liquidações antecipadas (documentação do BCB).")

    tentar(simples, "copom_historico", "https://www.bcb.gov.br/api/servico/sitebcb/historicotaxasjuros",
           f"BCB_historico-taxas-juros-copom_{HOJE}.json", "Histórico das taxas de juros (reuniões do Copom)",
           "Banco Central do Brasil — API do site", "% a.a.", "por reunião")

    tentar(simples, "embi_brasil", "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='JPM366_EMBI366')",
           f"IPEADATA_JPM366_EMBI366_{HOJE}.json", "EMBI+ Risco-Brasil (JPM366_EMBI366)", "Ipeadata / JP Morgan",
           "pontos-base", "diária")
    tentar(simples, "embi_brasil_metadados", "http://www.ipeadata.gov.br/api/odata4/Metadados('JPM366_EMBI366')",
           f"IPEADATA_JPM366_EMBI366_metadados_{HOJE}.json", "Metadados EMBI+ Risco-Brasil", "Ipeadata", "-", "-")

    tentar(simples, "tesouro_estoque_dpf",
           "https://www.tesourotransparente.gov.br/ckan/dataset/0998f610-bc25-4ce3-b32c-a873447500c2/resource/b6280ed3-ef7e-4569-954a-bded97c2c8a1/download/estoquedpf.csv",
           f"TESOURO_estoque-dpf_{HOJE}.csv", "Estoque da Dívida Pública Federal", "Tesouro Nacional — Tesouro Transparente",
           "R$", "mensal")

    # Tabelas de estatísticas do setor externo do BCB (abril e outubro de cada ano disponível)
    for ano in range(2019, 2027):
        for mes in ("04", "10"):
            ym = f"{ano}{mes}"
            if ym > dt.date.today().strftime("%Y%m"):
                continue
            tentar(simples, f"bcb_setor_externo_{ym}",
                   f"https://www.bcb.gov.br/content/estatisticas/hist_estatisticassetorexterno/{ym}_Tabelas_de_estatisticas_do_setor_externo.xlsx",
                   f"BCB_tabelas-setor-externo_{ym}.xlsx", f"Tabelas de estatísticas do setor externo ({ym})",
                   "Banco Central do Brasil — estatísticas do setor externo", "US$ milhões", "trimestral/mensal",
                   "Tabelas 15 (dívida externa), 16 (cronograma de amortização), 18 (PII passivos), 14 (reservas).")

    # Arquivos do FMI já fornecidos pelo Pedro
    for suf, desc in (("a", "Brasil, China, Índia, Rússia, África do Sul"), ("b", "todos os países")):
        arq = BRUTOS / f"IMF-DataMapper_ReservasAdequacao_export-20261123_{suf}.xls"
        if arq.exists():
            registrar(id_interno=f"fmi_ara_ratio_{suf}", nome_na_fonte="Ratio of reserve/ARA metric (Unit)",
                      fonte="FMI DataMapper — exportado pelo Pedro", url_ou_endpoint="https://www.imf.org/external/datamapper",
                      unidade="razão (reservas/ARA)", frequencia="anual", periodo_inicio="2000", periodo_fim="2026",
                      data_hora_acesso="2026-11-23", arquivo_bruto=arq.name, sha256=sha256(arq),
                      observacoes=f"{desc}. FMI marca 'Estimates start after 2021'. Ler com xlrd ignore_workbook_corruption=True.")

    pend = BRUTOS.parent / "03_dicionario" / f"pendencias_download_{HOJE}.json"
    pend.write_text(json.dumps(FALHAS, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"FIM. Falhas: {len(FALHAS)} (detalhe em {pend.name})")
