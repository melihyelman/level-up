# submission csv -> box df (image_id,label,conf,x,y,w,h)
import pandas as pd
def parse_sub(f):
    s=pd.read_csv(f);rows=[]
    for i,p in zip(s.image_id,s.PredictionString):
        if pd.isna(p) or p=='none':
            continue
        t=p.split()
        for k in range(0,len(t),6):
            rows.append((i,t[k],float(t[k+1]),*map(float,t[k+2:k+6])))
    return pd.DataFrame(rows,columns=['image_id','label','conf','x','y','w','h'])
