import numpy as np,pandas as pd,sys,statsmodels.api as sm
from pathlib import Path
sys.path.insert(0,'03_Codigo');from src.simulacao import Blocos,sortear_sequencias,simular
T=Path('04_Resultados/tabelas'); D=Path('02_Dados/02_tratados');N=10000;H=48;seed=20261123
R0=367.558;S0=93.25;cap=114.918;floor=336.5503787164058
bdf=pd.read_csv(T/'episodios_blocos.csv')
def summarize(t): return [round(100*np.mean(t<=h),1) for h in [12,24,48]]+[int(np.median(t)) if np.mean(t<=48)>.5 else '>48']
for e in ['nenhum',*bdf.episodio.unique()]:
 b=Blocos.de_tabela(bdf[bdf.episodio!=e]);idx=sortear_sequencias(b,N,H,np.random.default_rng(seed));out=simular(b,idx,np.ones(H),R0,floor,S0,cap,True);print('LOO',e,summarize(out['T_F']))
# Monthly data all complete months, modern sample
at=pd.read_csv(D/'atuacoes_cambio.csv',parse_dates=['data','data_liquidacao','data_vencimento']); fx=pd.read_csv(D/'cambio_diario.csv',parse_dates=['data']).set_index('data').cambio_brl_usd.resample('MS').last(); sel=pd.read_csv(D/'meta_selic_diaria.csv',parse_dates=['data']).set_index('data').meta_selic.resample('MS').last();emb=pd.read_csv(D/'embi_diario.csv',parse_dates=['data']).set_index('data').embi_pb.resample('MS').last();st=pd.read_csv(D/'estoques_swap_linha_diario.csv',parse_dates=['data']).set_index('data').swap_liquido_usd_bi.resample('MS').last();
idxm=pd.date_range('2004-01-01','2026-09-01',freq='MS');m=pd.DataFrame(index=idxm);m['fx']=fx;m['dep']=100*np.log(fx).diff();m['sel']=sel;m['ds']=sel.diff();m['emb']=emb;m['de']=emb.diff()/100;m['sw']=st.diff();
a=at[at.instrumento.isin(['Venda a Vista','Compra a Vista','Compra a Termo'])].copy();a['signed']=a.volume_aceito_usd_bi*np.where(a.instrumento=='Venda a Vista',1,-1);m['spot']=a.groupby(a.data_liquidacao.dt.to_period('M').dt.to_timestamp()).signed.sum().reindex(idxm,fill_value=0)
l=at[at.instrumento.isin(['Venda com Recompra','Empréstimo','Operação Compromissada'])].dropna(subset=['data_liquidacao','data_vencimento']).copy();l['month']=l.data_liquidacao.dt.to_period('M').dt.to_timestamp();l['lag']=(l.data_vencimento.dt.year-l.data_liquidacao.dt.year)*12+l.data_vencimento.dt.month-l.data_liquidacao.dt.month;l['lag']=l['lag'].clip(lower=0,upper=36);tab=l.pivot_table(index='month',columns='lag',values='volume_aceito_usd_bi',aggfunc='sum',fill_value=0).reindex(index=idxm,columns=range(37),fill_value=0).fillna(0);m['temp']=tab.sum(axis=1)
q=m.dep.quantile(.8);reg=(m.dep>=q).astype(int).values;trans=pd.crosstab(reg[:-1],reg[1:],normalize='index').values;print('SAMPLE',len(m),q,trans,'means',m.groupby(reg)[['dep','spot','temp','sw']].mean().to_string()); print('missing',m.isna().sum().to_dict())
# noncausal monthly regression and historical decisions, with controls available
r=pd.DataFrame({'dep':m.dep,'ds':m.ds,'de':m.de,'dep_lag':m.dep.shift(),'sel_lag':m.sel.shift()}).dropna();fit=sm.OLS(r.dep,sm.add_constant(r.drop(columns='dep'))).fit(cov_type='HAC',cov_kwds={'maxlags':3});print('REG',len(r),fit.rsquared, pd.DataFrame({'beta':fit.params,'lo':fit.conf_int()[0],'hi':fit.conf_int()[1],'p':fit.pvalues}).to_string());
e=pd.read_csv(T/'etapa2b_eventos_copom.csv');e=e[e.tipo=='corte'];x=e.variacao_cambio_pct[e.meta_anterior<10];y=e.variacao_cambio_pct[e.meta_anterior>=10];from scipy.stats import ttest_ind; print('WELCH',len(x),len(y),x.mean()-y.mean(),ttest_ind(x,y,equal_var=False))
# regime draws, start stressed and then transition; scenario stress all or normal history
rng=np.random.default_rng(seed);u=rng.random((N,H));v=rng.random((N,H));pools=[np.flatnonzero(reg==i) for i in [0,1]]
def paths(mode):
 state=np.ones(N,dtype=int);ix=np.empty((N,H),int)
 for t in range(H):
  if mode=='normal': state[:]=0
  if mode=='stress': state[:]=1
  ix[:,t]=np.where(state==1,pools[1][(v[:,t]*len(pools[1])).astype(int)],pools[0][(v[:,t]*len(pools[0])).astype(int)])
  if mode=='markov':state=(u[:,t]<trans[state,1]).astype(int)
 return ix
# own repayments from outstanding existing lines, exact months
existing=np.zeros(H);existing[0]=2.05;existing[2]=1;existing[4]=1
spot=m.spot.to_numpy();sw=m.sw.to_numpy();dep=m.dep.to_numpy();line=tab.to_numpy()
def sim(mode='markov',lam=1,sub=.5,ceiling=cap,piso=floor,dynamic=False,aport=0,delta=0):
 ix=paths(mode);R=np.full(N,R0);S=np.full(N,S0);ret=np.zeros((N,H+37));tt=np.full(N,np.inf);fxrel=np.ones(N);tr=np.full(N,np.inf)
 for t in range(H):
  ii=ix[:,t];scale=lam*(1-delta if t>=12 else 1);R+=ret[:,t]+existing[t]+(aport if t==0 else 0);fxrel*=np.exp(dep[ii]/100) if dynamic else 1
  # illustrative dynamic: BRL broad money nominal fixed, other components fixed in USD
  F=piso-152.2865322895+152.2865322895/fxrel if dynamic else piso
  a=spot[ii]*scale;s=sw[ii]*scale;L=line[ii]*scale;R+=np.maximum(-a,0);S+=np.minimum(s,0);a=np.maximum(a,0);s=np.maximum(s,0)
  # same-month maturities net out; other temporary lines cannot be replaced by swaps
  L[:,0]=0;d=L.sum(axis=1);exe=np.minimum(d,np.maximum(R-F,0));ratio=np.divide(exe,d,out=np.zeros(N),where=d>0);R-=exe;ret[:,t+1:t+37]+=L[:,1:]*ratio[:,None];lackL=d-exe
  er=np.minimum(a,np.maximum(R-F,0));es=np.minimum(s,np.maximum(ceiling-S,0));R-=er;S+=es;lr=a-er;ls=s-es
  exs=np.minimum(sub*lr,np.maximum(ceiling-S,0));exr=np.minimum(sub*ls,np.maximum(R-F,0));S+=exs;R-=exr;fail=lackL+lr-exs+ls-exr>1e-6;tt[fail&np.isinf(tt)]=t+1;tr[(R<=F+1e-6)&np.isinf(tr)]=t+1
 return summarize(tt),summarize(tr)
for mode in ['stress','markov','normal']:
 for lam in [.5,1,1.5,2]:print('SIM',mode,lam,sim(mode,lam))
for sub in [0,.5,1]:
 for ceiling in [cap,cap*1.25,cap*1.5]:print('SENS',sub,ceiling,sim(sub=sub,ceiling=ceiling))
for p in [258.8293,319.4484,floor,167.7635]:print('PISO',p,sim(piso=p))
print('DYN',sim(dynamic=True));print('APORTE',sim(aport=9.04));print('DELTA',sim(delta=.207));print('BOTH',sim(aport=9.04,delta=.207))
