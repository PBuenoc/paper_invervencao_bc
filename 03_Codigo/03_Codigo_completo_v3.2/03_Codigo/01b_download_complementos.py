"""
Séries SGS:
  29722  Estoque de Linhas com Recompra - diária (US$ milhões)
  29723  Estoque de Swap Cambial - Nocional - diária (US$ milhões)
  29724  Estoque de Swap Cambial - Número de contratos - diária (unidades)
  13961  Movimento de câmbio contratado - saldo (US$ milhões, diária)
  13967  Câmbio contratado - Operações no segmento comercial - saldo (US$ milhões, diária)
  13970  Câmbio contratado - Operações com cliente no segmento financeiro - saldo (US$ milhões, diária)
  4385   PIB mensal - Em US$ milhões (mensal)
  13962  Câmbio contratado - operações com clientes no segmento comercial - exportação - total (US$ milhões, diária)

"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import BRUTOS, HEADERS, HOJE, agora, log, registrar, sha256  # noqa: E402

REFRESH = "--refresh" in sys.argv

SERIES = {
    29722: ("linhas_estoque_oficial_diario", dt.date(2001, 1, 1)),
    29723: ("swap_estoque_nocional_oficial_diario", dt.date(2001, 1, 1)),
    29724: ("swap_contratos_oficial_diario", dt.date(2001, 1, 1)),
    13961: ("fluxo_cambial_total_diario", dt.date(1990, 1, 1)),
    13967: ("fluxo_cambial_comercial_diario", dt.date(1990, 1, 1)),
    13970: ("fluxo_cambial_financeiro_diario", dt.date(1990, 1, 1)),
    4385: ("pib_mensal_usd", dt.date(1990, 1, 1)),
    13962: ("cambio_contratado_exportacao_diario", dt.date(1990, 1, 1)),
}

SOAP = ('<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope '
        'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:pub="http://publico.ws.casosdeuso.sgs.pec.bcb.gov.br"><soapenv:Header/><soapenv:Body>'
        '<pub:getUltimoValorXML><in0>{c}</in0></pub:getUltimoValorXML></soapenv:Body></soapenv:Envelope>')


def metadados(codigo: int) -> dict:
    r = requests.post("https://www3.bcb.gov.br/wssgs/services/FachadaWSSGS", data=SOAP.format(c=codigo),
                      headers={**HEADERS, "Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'}, timeout=60)
    r.raise_for_status()
    t = html.unescape(r.text)
    out = {}
    for tag in ("NOME", "UNIDADE", "PERIODICIDADE"):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", t, re.S)
        out[tag.lower()] = m.group(1).strip() if m else ""
    return out


def janela(url: str, codigo: int, ini: dt.date, fim: dt.date) -> list[dict]:
    """Baixa uma janela; 404 = sem dados; 304 espúrio (cache do proxy) = divide a janela ao meio."""
    params = {"formato": "json", "dataInicial": ini.strftime("%d/%m/%Y"), "dataFinal": fim.strftime("%d/%m/%Y")}
    for tentativa in range(1, 5):
        try:
            r = requests.get(url, params=params, timeout=120,
                             headers={**HEADERS, "Cache-Control": "no-cache", "Pragma": "no-cache"})
            log(f"GET {r.url} -> {r.status_code} ({len(r.content)} bytes) tentativa {tentativa}")
            if r.status_code == 200:
                dados = r.json()
                return [{"janela": [ini.isoformat(), fim.isoformat()], "dados": dados if isinstance(dados, list) else []}]
            if r.status_code == 404:
                return [{"janela": [ini.isoformat(), fim.isoformat()], "dados": []}]
            if r.status_code == 304 and (fim - ini).days > 40:
                meio = ini + (fim - ini) / 2
                log(f"304 em {params['dataInicial']}-{params['dataFinal']}: dividindo a janela")
                return janela(url, codigo, ini, meio) + janela(url, codigo, meio + dt.timedelta(days=1), fim)
        except Exception as e:  # noqa: BLE001
            log(f"ERRO {codigo} {params['dataInicial']}-{params['dataFinal']} tentativa {tentativa}: {e}")
        time.sleep(4 * tentativa)
    raise RuntimeError(f"janela {params['dataInicial']}-{params['dataFinal']} falhou")


def baixar_serie(codigo: int) -> None:
    id_, inicio = SERIES[codigo]
    destino = BRUTOS / f"BCB-SGS_{codigo}_{id_}_{HOJE}.json"
    meta = metadados(codigo)
    log(f"META {codigo}: {meta}")
    if destino.exists() and not REFRESH:
        log(f"CACHE {destino.name}")
    else:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
        blocos, ini, fim_total = [], inicio, dt.date.today()
        while ini <= fim_total:
            fim = min(dt.date(ini.year + 4, 12, 31), fim_total)
            blocos.extend(janela(url, codigo, ini, fim))
            ini = fim + dt.timedelta(days=1)
        destino.write_text(json.dumps({"codigo_sgs": codigo, "url": url, "metadados_ws": meta, "blocos": blocos},
                                      ensure_ascii=False), encoding="utf-8")
        log(f"SALVO {destino.name} sha256={sha256(destino)}")
    conteudo = json.loads(destino.read_text(encoding="utf-8"))
    obs = [o for b in conteudo["blocos"] for o in b["dados"]]
    registrar(id_interno=id_, nome_na_fonte=meta.get("nome", ""), fonte="Banco Central do Brasil — SGS",
              url_ou_endpoint=f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados", codigo=str(codigo),
              unidade=meta.get("unidade", ""), frequencia=meta.get("periodicidade", ""),
              periodo_inicio=obs[0]["data"] if obs else "", periodo_fim=obs[-1]["data"] if obs else "",
              data_hora_acesso=agora(), arquivo_bruto=destino.name, sha256=sha256(destino),
              n_observacoes=str(len(obs)),
              observacoes="Metadados conferidos no web service SGS (getUltimoValorXML); série ausente do catálogo "
                          "CKAN na data do acesso. Incluída na auditoria da segunda rodada.")
    log(f"OK {codigo} {id_}: {len(obs)} obs, {obs[0]['data'] if obs else '-'} a {obs[-1]['data'] if obs else '-'}")


if __name__ == "__main__":
    pend = []
    for c in SERIES:
        try:
            baixar_serie(c)
        except Exception as e:  # noqa: BLE001
            log(f"PENDENCIA {c}: {e}")
            pend.append((c, str(e)))
    print("PENDENCIAS:", pend)
