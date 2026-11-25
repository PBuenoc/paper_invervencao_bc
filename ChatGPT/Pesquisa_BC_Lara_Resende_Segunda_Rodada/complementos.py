"""Exporta bases intermediárias e refaz projeções locais exploratórias."""
from pathlib import Path
import pandas as pd, numpy as np, statsmodels.api as sm, re, ast
OUT=Path('04_Resultados/segunda_rodada')
# Reutiliza preparação de dados da revisão, sem simulações repetidas.
src=Path('revisao.py').read_text();exec(src[:src.index("for e in ['nenhum'")]+src[src.index('# Monthly data'):src.index('# regime draws')])
m.assign(regime_estresse=reg).to_csv(OUT/'base_mensal_regimes.csv',index_label='data')
rows=[]
for h in [0,1,3,6,12]:
    target=100*(np.log(m.fx.shift(-h))-np.log(m.fx.shift(1)))
    d=pd.DataFrame({'y':target,'ds':m.ds,'de':m.de,'dep_lag':m.dep.shift(),'sel_lag':m.sel.shift()}).dropna()
    fit=sm.OLS(d.y,sm.add_constant(d.drop(columns='y'))).fit(cov_type='HAC',cov_kwds={'maxlags':max(3,h+1)})
    lo,hi=fit.conf_int().loc['ds'];rows.append({'horizonte_meses':h,'n':len(d),'resposta_corte_1pp':-fit.params.ds,'ic95_inf':-hi,'ic95_sup':-lo,'p':fit.pvalues.ds})
pd.DataFrame(rows).to_csv(OUT/'projecoes_locais_reestimadas.csv',index=False)
# Recupera fluxos oficiais já arquivados, e exporta base extraída.
exec(Path('fluxo.py').read_text().split('# regression')[0]);f.to_csv(OUT/'fluxo_cambial_mensal.csv',index_label='data')
# Compara agregado monetário com o quadro do Article IV 2026; valores do FMI em R$ bi, transcritos.
fmi=pd.Series([8584.2,9490.9,10966.7,12326.6,13509.0],index=range(2021,2026));ag=pd.DataFrame({'FMI_moeda_ampla_R$_bi':fmi})
for key,code in [('M2','27810'),('M3','27813'),('M4','27815')]:
    fpath=next(Path('02_Dados/01_brutos').glob(f'*{code}*json'));a=pd.DataFrame([r for b in __import__('json').loads(fpath.read_text())['blocos'] for r in b['dados']]);a['data']=pd.to_datetime(a.data,dayfirst=True);a['valor']=pd.to_numeric(a.valor);a=a[a.data.dt.month==12].set_index(a[a.data.dt.month==12].data.dt.year);ag[key+'_BCB_R$_bi']=a.valor/1e6
ag.to_csv(OUT/'comparacao_agregados_monetarios.csv',index_label='ano')
# Consolida resultados numéricos emitidos pelos scripts anteriores.
rows=[]
for filename in ['revisao','extensao','final_checks']:
    for line in (OUT/(filename+'.txt')).read_text().splitlines():
        if not re.match(r'^(LOO|SIM|SENS|PISO|DYN|APORTE|DELTA|BOTH|FRONTIER|MAT|COND|PROXY|INCOME)\b',line):continue
        start=line.find('([') if '([' in line else line.find('[')
        if start<0:continue
        prefix=line[:start].strip();val=ast.literal_eval(re.sub(r'np\.float64\(([^)]+)\)',r'\1',line[start:]));parts=val if isinstance(val,tuple) else (val,)
        for metric,arr in zip(['primeira_demanda_nao_atendida','reservas_no_piso'],parts):
            rows.append([filename,prefix,metric,*arr])
pd.DataFrame(rows,columns=['script','cenario','metrica','prob_12_pct','prob_24_pct','prob_48_pct','mediana_meses']).to_csv(OUT/'simulacoes_consolidadas.csv',index=False)
