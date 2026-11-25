# re-use local functions; don't repeat main simulations
src=open('revisao.py').read();src=src[:src.index("for mode in ['stress'")];src=src[:src.index("for e in ['nenhum'")]+src[src.index('# Monthly data'):];exec(src)
# logistic conditional model: actual stress defined using fixed empirical threshold; estimates not causal
rr=pd.DataFrame({'stress':reg,'prev':pd.Series(reg,index=m.index).shift(),'ds':m.ds,'de':m.de},index=m.index).dropna();logit=sm.Logit(rr.stress,sm.add_constant(rr[['prev','ds','de']])).fit(disp=0,cov_type='HC1');print('LOGIT',len(rr),pd.DataFrame({'b':logit.params,'lo':logit.conf_int()[0],'hi':logit.conf_int()[1],'p':logit.pvalues}).to_string());
# operational frontier, tested lambda grid
for lam in [.1,.2,.3,.4,.5,.6,.7,.8,.9,1]: print('FRONTIER',lam,sim(lam=lam)[0]);
# alternative first materially unserved demand >= 1 bi (not just epsilon)
src2=open('revisao.py').read();fn=src2[src2.index('def sim('):src2.index("for mode in ['stress'")];fn=fn.replace('def sim(', 'def sim_material(').replace('lackL+lr-exs+ls-exr>1e-6','lackL+lr-exs+ls-exr>=1.0');exec(fn)
for sub in [0,.25,.5,.75,1]: print('MAT',sub,sim_material(sub=sub)[0]);
# forecast only conditional on assumed risk scenario and Selic path, not predictions
orig_paths=paths
def logistic_paths(rates,risk):
 state=np.ones(N,dtype=int);ix=np.empty((N,H),int);pr=[]
 for t in range(H):
  coef=logit.params;z=coef['const']+coef['prev']*state+coef['ds']*rates[t]+coef['de']*risk[t];p=1/(1+np.exp(-z));pr.append(p.mean());state=(u[:,t]<p).astype(int)
  ix[:,t]=np.where(state==1,pools[1][(v[:,t]*len(pools[1])).astype(int)],pools[0][(v[:,t]*len(pools[0])).astype(int)])
 return ix,np.array(pr)
for target in [14.25,10,7.5,5.5]:
 for risk in [-1,0,1]:
  rates=np.zeros(H);rates[:12]=(target-14.25)/12; dr=np.zeros(H);dr[:12]=risk/12
  pi,pp=logistic_paths(rates,dr);paths=lambda mode:pi
  print('COND',target,risk,np.round(pp[:12].mean(),3),sim()[0])
paths=orig_paths
# synthetic fiscal dynamics, 80% starting debt, 12.7% avg cost, share 51.2% reprices at selic; rest gradually rolls to policy + premium
for target in [14.25,7.5,5.5]:
 for premium in [0,4]:
  for pddef in [0,1]:
   rate=14.25+(target-14.25)*np.minimum(np.arange(1,49)/12,1);non=(12.7-.512*14.25)/.488;debt=.80;ds=[]
   for t in range(H):
    non=non+(rate[t]+premium-non)/48 # illustrative rollover rate
    eff=.512*rate[t]+.488*non
    debt=debt*((1+eff/100)/(1+.055))**(1/12)+pddef/100/12
    if t in [11,23,47]:ds.append(round(debt*100,2))
   print('DEBT',target,premium,pddef,ds)
