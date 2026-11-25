import pandas as pd,numpy as np,glob,statsmodels.api as sm
from pathlib import Path
D=Path('02_Dados/02_tratados');months={x:i+1 for i,x in enumerate('Jan Fev Mar Abr Mai Jun Jul Ago Set Out Nov Dez'.split())};flows={};stocks={}
for f in sorted(glob.glob('02_Dados/01_brutos/*setor-externo*')):
 x=pd.ExcelFile(f);ix=pd.read_excel(x,sheet_name='Índice',header=None)
 for row in ix.itertuples(index=False,name=None):
  if len(row)<2:continue
  if 'Câmbio contratado e posição de câmbio' in str(row[1]):
   d=pd.read_excel(x,sheet_name=row[0],header=None);year=None
   for a in d.itertuples(index=False,name=None):
    if isinstance(a[0],(int,float)) and pd.notna(a[0]) and 1900<a[0]<2100:year=int(a[0])
    if isinstance(a[1],str) and a[1].strip() in months and year:
     try:
      commercial,financial,total=[float(a[j])/1000 for j in [7,10,11]]
      if abs(commercial+financial-total)<1e-4:flows[pd.Timestamp(year,months[a[1].strip()],1)]=[commercial,financial,total]
     except:pass
  if 'Demonstrativo de variação das reservas' in str(row[1]):
   d=pd.read_excel(x,sheet_name=row[0],header=None); yr=None
   for col in range(1,d.shape[1]):
    y=d.iloc[4,col]; mon=d.iloc[6,col]
    if pd.notna(y):
     try: yr=int(y)
     except: pass
    if not isinstance(mon,str) or mon.strip() not in months or yr is None:continue
    try:
     j=d[0].astype(str).str.contains('Saldo de linhas com recompra',case=False).idxmax(); val=float(d.iloc[j,col])/1000
     if d[0].astype(str).str.contains('Saldo de linhas com recompra',case=False).any():stocks[pd.Timestamp(yr,months[mon.strip()],1)]=val
    except:pass
f=pd.DataFrame.from_dict(flows,orient='index',columns=['com','fin','total']).sort_index();print('FLOW',len(f),f.index.min(),f.index.max(),f.isna().sum(),f.tail(12).to_string());print('GAPS',pd.date_range(f.index.min(),f.index.max(),freq='MS').difference(f.index));print('LINES JUNE',stocks.get(pd.Timestamp('2026-06-01')))
# regression
fx=pd.read_csv(D/'cambio_diario.csv',parse_dates=['data']).set_index('data').cambio_brl_usd.resample('MS').last();sel=pd.read_csv(D/'meta_selic_diaria.csv',parse_dates=['data']).set_index('data').meta_selic.resample('MS').last();emb=pd.read_csv(D/'embi_diario.csv',parse_dates=['data']).set_index('data').embi_pb.resample('MS').last();r=pd.DataFrame({'dep':100*np.log(fx).diff(),'ds':sel.diff(),'de':emb.diff()/100,'dep_lag':100*np.log(fx).diff().shift(),'sel_lag':sel.shift()}).join(f);r=r.dropna();fit=sm.OLS(r.dep,sm.add_constant(r[['ds','de','dep_lag','sel_lag','fin','com']])).fit(cov_type='HAC',cov_kwds={'maxlags':3});print('REG FLOW',len(r),r.index.min(),r.index.max(),fit.rsquared,pd.DataFrame({'b':fit.params,'lo':fit.conf_int()[0],'hi':fit.conf_int()[1],'p':fit.pvalues}).to_string());print('FLOW moments',f.describe().to_string())
# fiscal annualized LFT stock constant, linear path monthly rates
lft=4.567284e12;start=14.25
for end in [10,7.5,5.5]:
 for n in [12,24,48]:
  rates=start+(end-start)*np.minimum(np.arange(1,49)/n,1);saving=lft*(start-rates)/100/12;print('FISC',end,n,np.round([saving[:12].sum()/1e9,saving[:24].sum()/1e9,saving[:48].sum()/1e9,lft*(start-end)/100/1e9],1))
