src=open('revisao.py').read();src=src[:src.index("for mode in ['stress'")];src=src[:src.index("for e in ['nenhum'")]+src[src.index('# Monthly data'):];exec(src)
# preferred monetary aggregate proxy, still uncertain
f=321.4640429826359
for l in [.3,.4,.5,1,1.5,2]:print('PROXY',l,sim(lam=l,piso=f))
# check official balance vs reconstruction from dated cash lines, month end 2018-2026
# calculate non-intervention reserve income/valuation from official tables
import glob
mon={x:i+1 for i,x in enumerate('Jan Fev Mar Abr Mai Jun Jul Ago Set Out Nov Dez'.split())};vals={}
for fl in sorted(glob.glob('02_Dados/01_brutos/*setor-externo*')):
 x=pd.ExcelFile(fl);ii=pd.read_excel(x,sheet_name='Índice',header=None);a=ii[ii[1].astype(str).str.contains('Demonstrativo de variação das reservas',case=False)];
 if a.empty:continue
 d=pd.read_excel(x,sheet_name=a.iloc[0,0],header=None);yr=None; names=d[0].astype(str).str.strip();cols={k:names[names.str.fullmatch(k,case=False)].index.tolist() for k in ['Variação total','Intervenções do Banco Central','Receitas de juros','Saldo de linhas com recompra','Posição das reservas']};
 for col in range(1,d.shape[1]):
  y=d.iloc[4,col];mm=d.iloc[6,col]
  if pd.notna(y):
   try:yr=int(y)
   except:pass
  if not isinstance(mm,str) or mm.strip() not in mon or yr is None:continue
  try:vals[pd.Timestamp(yr,mon[mm.strip()],1)]={k:float(d.iloc[ls[0],col])/1000 for k,ls in cols.items() if ls}
  except:pass
x=pd.DataFrame.from_dict(vals,orient='index').sort_index();x['net_nonintervention']=x['Variação total']-x['Intervenções do Banco Central'];print('RESIDUAL',x.index.min(),x.index.max(),x.shape,x[['net_nonintervention','Receitas de juros']].describe().to_string());print('JUNE',x.loc['2026-06-01'].to_dict())
# additional reserve income scenario use observed mean monthly non-intervention change as fixed sensitivity, not projection
fun=open('revisao.py').read();fun=fun[fun.index('def sim('):fun.index("for mode in ['stress'")];fun=fun.replace('def sim(', 'def sim_income(').replace('delta=0):','delta=0,income=0):').replace('R+=ret[:,t]+existing[t]+','R+=income+ret[:,t]+existing[t]+');exec(fun)
for i in [0,float(x['Receitas de juros'].median()),float(x['net_nonintervention'].mean()),-1.0]:print('INCOME',i,sim_income(income=i,piso=f))
