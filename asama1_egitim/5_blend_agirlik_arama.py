# netflix-style blend: learn wbf model weights on the 647 test-like val imgs (all models trained on same split, none saw val)
# then apply to test. teammate (other split, no val) added afterwards with fixed weight
import warnings;warnings.filterwarnings('ignore')
import os,sys,json,random,itertools,numpy as np,pandas as pd
from PIL import Image
from ensemble_boxes import weighted_boxes_fusion
HERE=os.path.dirname(os.path.abspath(__file__));sys.path.insert(0,HERE)
from parse_sub import parse_sub
P=os.environ.get('ROKETSAN_ROOT','/Users/mehmet/Desktop/rocketsan');   # data/ ve runs/ klasorlerinin koku
DATA=f'{P}/data/level-up-ai-roketsan-yapay-zeka-hackathonu';R=f'{P}/runs';O=f'{R}/09_blend'
CLASSES=CL=['car','van','truck','bus'];C2I={c:i for i,c in enumerate(CL)}
# evaluate() = notebook'taki yerel metrik hucresi
nb=json.load(open(f'{HERE}/2_egitim_carunder_m1280.ipynb'));src=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code']
exec([x for x in src if 'def evaluate' in x][0].split('gt_val=')[0])
ann=pd.read_csv(f'{DATA}/train/annotations.csv');imgs=sorted(f[:-4] for f in os.listdir(f'{DATA}/train/images'))
sizes={i:Image.open(f'{DATA}/train/images/{i}.jpg').size for i in imgs}
tsz=pd.Series([Image.open(f'{DATA}/test/images/{f}').size for f in os.listdir(f'{DATA}/test/images')]).value_counts(normalize=True)
bysz={}
for i in imgs:
    bysz.setdefault(sizes[i],[]).append(i)
random.seed(42);val=[];nval=int(len(imgs)*0.1)
for s_,sh in tsz.items():
    pool=bysz.get(s_,[]);val+=random.sample(pool,min(len(pool)//3,round(nval*sh)))
val=sorted(val);gt=ann[ann.image_id.isin(val)];vsz={i:sizes[i] for i in val}
T_dir=f'{DATA}/test/images';tsz_={f[:-4]:Image.open(f'{T_dir}/{f}').size for f in os.listdir(T_dir)}
def load(path):
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path) if path.endswith('.parquet') else parse_sub(path)
# name: (val file, test file, rule_risk)
MODELS={
 'night_grid8':(f'{R}/07_p4_carunder_yolo26l_1536/val_pred_tta_grid8.parquet',f'{R}/07_p4_carunder_yolo26l_1536/submission_tta_grid8.csv',0),
 'carunder_tta':(f'{R}/05_p3_carunder_sh0.8_e20/carunder_val_tta.parquet',f'{R}/05_p3_carunder_sh0.8_e20/submission_tta.csv',0),
 'patch':(f'{R}/03_p2_patch/val_pred.parquet',f'{R}/03_p2_patch/test_pred_raw.parquet',0),
 #'patch_clahe':(f'{R}/04_p2_patch_clahe_e28/val_pred.parquet',f'{R}/04_p2_patch_clahe_e28/clahe_test_raw.parquet',0),
 #'rfdetr':(f'{R}/02_rfdetr_m896/val_pred.parquet',f'{R}/02_rfdetr_m896/test_pred_raw.parquet',1),
}
Vd,Td,RISK={},{},{}
for n,(vf,tf,rk) in MODELS.items():
    v=load(vf)
    if v is None:
        print('skip',n,'(no val file)');continue
    Vd[n]=v[v.image_id.isin(val)];Td[n]=load(tf);RISK[n]=rk
    print('loaded',n,'val',len(Vd[n]),'test',None if Td[n] is None else len(Td[n]))
GV={n:dict(tuple(d.groupby('image_id'))) for n,d in Vd.items()}
def wbf(groups,wts,sz,iou=0.65,ct='avg'):
    out=[]
    for i,(W,H) in sz.items():
        B,S,L=[],[],[]
        for g in groups:
            p=g.get(i)
            if p is None:
                B.append(np.zeros((0,4)));S.append(np.zeros(0));L.append(np.zeros(0));continue
            B.append(np.c_[p.x/W,p.y/H,(p.x+p.w)/W,(p.y+p.h)/H].clip(0,1));S.append(p.conf.values);L.append(p.label.map(C2I).values)
        if not any(len(x) for x in S):
            continue
        b,s,l=weighted_boxes_fusion(B,S,L,weights=wts,iou_thr=iou,skip_box_thr=0.0002,conf_type=ct)
        out.append(pd.DataFrame(dict(image_id=i,label=[CL[int(k)] for k in l],conf=s,x=b[:,0]*W,y=b[:,1]*H,w=(b[:,2]-b[:,0])*W,h=(b[:,3]-b[:,1])*H)))
    return pd.concat(out,ignore_index=True)
cache={}
def score(names,wts,iou=0.65,ct='avg'):
    k=(tuple(names),tuple(wts),iou,ct)
    if k not in cache:
        p=Vd[names[0]] if len(names)==1 else wbf([GV[n] for n in names],list(wts),vsz,iou,ct)
        cache[k]=evaluate(p,gt,pred_min=100,verbose=False)
    return cache[k]
def search(pool):
    # coordinate ascent over integer weights 0..3 (0 = model dropped), start: all 1
    names=list(pool);w=[1]*len(names);best=score(names,w)[0]
    improved=True
    while improved:
        improved=False
        for j in range(len(names)):
            for cand in [0,1,2,3]:
                if cand==w[j]:
                    continue
                w2=w.copy();w2[j]=cand;keep=[n for n,x in zip(names,w2) if x>0];kw=[x for x in w2 if x>0]
                if not keep:
                    continue
                m=score(keep,kw)[0]
                if m>best+0.0003:
                    best,w,improved=m,w2,True
    keep=[n for n,x in zip(names,w) if x>0];kw=[x for x in w if x>0]
    bi=max([(score(keep,kw,iou,ct)[0],iou,ct) for iou in [0.6,0.65,0.7] for ct in ['avg','box_and_model_avg']])
    return keep,kw,bi
if __name__=='__main__':
    print('== singles');[print(f'{score([n],[1])[0]:.4f}',n) for n in Vd]
    res={}
    for tag,pool in [('safe',[n for n in Vd if not RISK[n]]),('with_rfdetr',list(Vd))]:
        keep,kw,(m,iou,ct)=search(pool);aps=score(keep,kw,iou,ct)[1]
        res[tag]=dict(models=keep,weights=kw,iou=iou,ct=ct,map50=m,aps=aps)
        print(f'== {tag}: {m:.4f}',dict(zip(keep,kw)),'iou',iou,ct,{c:round(aps[c],3) for c in CL},flush=True)
    json.dump(res,open(f'{O}/blend_weights.json','w'),indent=1,default=float)
    sub=pd.read_csv(f'{DATA}/sample_submission.csv')
    def write(E,path):
        E=E[E.w*E.h>=100]
        s={k:' '.join(f'{r.label} {r.conf:.5f} {r.x:.1f} {r.y:.1f} {r.w:.1f} {r.h:.1f}' for r in v.itertuples()) for k,v in E.groupby('image_id')}
        o=sub.copy();o['PredictionString']=o.image_id.map(s).fillna('none');o.to_csv(path,index=False);print(path,'none',(o.PredictionString=='none').sum())
    TM=pd.read_parquet(f'{R}/06_merge_teammate/teammate_test.parquet')
    for tag,r in res.items():
        if any(Td[n] is None for n in r['models']):
            print(tag,'missing test preds for',[n for n in r['models'] if Td[n] is None]);continue
        G=[dict(tuple(Td[n].groupby('image_id'))) for n in r['models']]
        E=wbf(G,r['weights'],tsz_,r['iou'],r['ct']);E.to_parquet(f'{O}/test_blend_{tag}.parquet')
        write(E,f'{O}/submission_blend_{tag}.csv')
        # teammate on top, weight = total blend weight (i.e. 50/50 with our blend)
        write(wbf([dict(tuple(E.groupby('image_id'))),dict(tuple(TM.groupby('image_id')))],[1,1],tsz_,0.7,'avg'),f'{O}/submission_blend_{tag}_plus_teammate.csv')
