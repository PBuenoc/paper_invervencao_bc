"""
Endpoint: ExpectativasMercadoSelic (campos Data, Reuniao, Mediana, Media, numeroRespondentes, baseCalculo).
baseCalculo = 0 (todas as respostas válidas). Um arquivo bruto com todos os anos.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).parent))
from src.comum import BRUTOS, HEADERS, HOJE, agora, log, registrar, sha256  # noqa: E402

URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoSelic"
REFRESH = "--refresh" in sys.argv

if __name__ == "__main__":
    destino = BRUTOS / f"BCB-Olinda_Focus_ExpectativasMercadoSelic_{HOJE}.json"
    if destino.exists() and not REFRESH:
        log(f"CACHE {destino.name}")
    else:
        anos = {}
        for ano in range(2004, dt.date.today().year + 1):
            params = {"$format": "json", "$top": "100000",
                      "$select": "Data,Reuniao,Mediana,Media,DesvioPadrao,numeroRespondentes,baseCalculo",
                      "$filter": f"baseCalculo eq 0 and Data ge '{ano}-01-01' and Data le '{ano}-12-31'"}
            for tentativa in range(1, 5):
                try:
                    r = requests.get(URL + "?" + urlencode(params, quote_via=quote), headers={**HEADERS, "Cache-Control": "no-cache"}, timeout=180)  # OData exige %20, não +
                    log(f"GET Focus Selic {ano} -> {r.status_code} ({len(r.content)} bytes)")
                    r.raise_for_status()
                    anos[str(ano)] = r.json()["value"]
                    break
                except Exception as e:  # noqa: BLE001
                    log(f"ERRO {ano} tentativa {tentativa}: {e}")
                    time.sleep(5 * tentativa)
            else:
                raise RuntimeError(f"Focus {ano} falhou")
        destino.write_text(json.dumps({"url": URL, "filtro": "baseCalculo eq 0", "anos": anos}, ensure_ascii=False), encoding="utf-8")
    d = json.loads(destino.read_text(encoding="utf-8"))
    n = sum(len(v) for v in d["anos"].values())
    registrar(id_interno="focus_selic_por_reuniao", nome_na_fonte="ExpectativasMercadoSelic (Focus)", fonte="Banco Central do Brasil — Olinda",
              url_ou_endpoint=URL, unidade="% a.a.", frequencia="diária (pesquisa Focus)", data_hora_acesso=agora(),
              arquivo_bruto=destino.name, sha256=sha256(destino), n_observacoes=str(n),
              observacoes="Mediana das expectativas para a meta Selic em cada reunião (campo Reuniao = Rk/AAAA); baseCalculo = 0.")
    log(f"OK Focus: {n} registros")
