"""Synthetic data only. Future labels are sampled from a known simulated relationship."""
from pathlib import Path
import numpy as np
import pandas as pd

def generate(n=1600,seed=42):
    rng=np.random.default_rng(seed)
    late=rng.poisson(1.5,n)
    missed=rng.binomial(3,.15,n)
    dpd=np.clip(rng.normal(10,12,n),0,60).round()
    income=rng.uniform(30000,180000,n).round()
    amount=rng.uniform(50000,900000,n).round()
    logits=-4+.7*late+1.1*missed+.055*dpd+.000001*amount
    return pd.DataFrame({'cust_id':['SYN-'+str(i) for i in range(n)],'loan_value':amount,'salary':income,'late_cnt':late,
      'missed_inst':missed,'dpd':dpd,'arrears_flag':rng.binomial(1,1/(1+np.exp(-logits)))})

if __name__=='__main__':
    out=Path('sample_data'); out.mkdir(exist_ok=True)
    df=generate()
    df.to_csv(out/'historical.csv',index=False)
    df.to_excel(out/'historical.xlsx',index=False)
    df.head(30).to_json(out/'partial.json',orient='records')
    df.drop(columns='arrears_flag').head(100).to_csv(out/'no_labels.csv',index=False)
    print('Synthetic datasets created in sample_data/')
