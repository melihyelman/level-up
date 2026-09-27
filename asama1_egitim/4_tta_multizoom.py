# ---- multi-zoom TTA, tuned on val (grid on 647 imgs: 1.0+flip+1.1+1.25+1.75+2.0 = +0.8 over 3-view) ----
# needs the notebook setup cells above (YOLO, evaluate, gt_val, val_ids, sizes, write_sub, RUNS, DATA)
import warnings;warnings.filterwarnings('ignore')
import os,numpy as np,pandas as pd,cv2
from PIL import Image
from ultralytics.utils import LOGGER;LOGGER.setLevel('ERROR')
from ensemble_boxes import weighted_boxes_fusion
TRUN=globals().get('TTA_RUN','p4_carunder_yolo26l_1536_e30')   # set TTA_RUN before exec to change
B=globals().get('TTA_B',1536)                                   # imgsz that run trained at (1280 for p3_carunder)
print('tta run',TRUN,'base',B)
TW=f'{RUNS}/{TRUN}/weights/best.pt';TD=f'{RUNS}/{TRUN}/tta_views';os.makedirs(TD,exist_ok=True)
def px(r):
    return int(round(B*r/32)*32)
# view = (zoom rel to B, flip, ultralytics augment)
CANDS={'cur3':[(1,0,0),(1,1,0),(1.25,0,0)],
       'grid6':[(1,0,0),(1,1,0),(1.1,0,0),(1.25,0,0),(1.75,0,0),(2.0,0,0)],
       'grid6_mild':[(1,0,0),(1,1,0),(1.1,0,0),(1.25,0,0),(1.45,0,0),(1.65,0,0)],   # same px as grid6 for a 1280 model
       'grid8':[(1,0,0),(1,1,0),(1.1,0,0),(1.25,0,0),(1.75,0,0),(2.0,0,0),(1,0,1),(1.25,1,0)]}
_M={}
def view(split,ids,img_dir,z,fl,ua):
    f=f'{TD}/{split}_{px(z)}_{fl}_{ua}.parquet'
    if os.path.exists(f):
        return pd.read_parquet(f)
    m=_M.setdefault('m',YOLO(TW));rows=[];bs=max(1,int(8/z**2))
    for s in range(0,len(ids),bs):
        chunk=ids[s:s+bs];ims=[cv2.imread(f'{img_dir}/{i}.jpg') for i in chunk]
        src=[np.ascontiguousarray(im[:,::-1]) for im in ims] if fl else ims
        res=m.predict(src,imgsz=px(z),conf=0.001,iou=0.6,max_det=1000,half=True,augment=bool(ua),verbose=False,nms=True)
        for i,im,r in zip(chunk,ims,res):
            b=r.boxes;xy=b.xyxy.cpu().numpy().copy()
            if fl:
                xy[:,[0,2]]=im.shape[1]-xy[:,[2,0]]
            for (x1,y1,x2,y2),p,k in zip(xy,b.conf.cpu().numpy(),b.cls.cpu().numpy().astype(int)):
                rows.append((i,CLASSES[k],float(p),x1,y1,x2-x1,y2-y1))
    d=pd.DataFrame(rows,columns=['image_id','label','conf','x','y','w','h']);d.to_parquet(f)
    print(split,'view',px(z),'flip' if fl else '','ultra' if ua else '','done',flush=True)
    return d
def fuse(dfs,sz,iou=0.65):
    C2I={c:i for i,c in enumerate(CLASSES)};gs=[dict(tuple(d.groupby('image_id'))) for d in dfs];out=[]
    for i,(Wd,Hd) in sz.items():
        Bx,S,L=[],[],[]
        for g in gs:
            p=g.get(i)
            if p is None:
                Bx.append(np.zeros((0,4)));S.append(np.zeros(0));L.append(np.zeros(0));continue
            Bx.append(np.c_[p.x/Wd,p.y/Hd,(p.x+p.w)/Wd,(p.y+p.h)/Hd].clip(0,1));S.append(p.conf.values);L.append(p.label.map(C2I).values)
        if not any(len(x) for x in S):
            continue
        b,s,l=weighted_boxes_fusion(Bx,S,L,iou_thr=iou,skip_box_thr=0.001,conf_type='avg')
        out.append(pd.DataFrame(dict(image_id=i,label=[CLASSES[int(k)] for k in l],conf=s,x=b[:,0]*Wd,y=b[:,1]*Hd,w=(b[:,2]-b[:,0])*Wd,h=(b[:,3]-b[:,1])*Hd)))
    return pd.concat(out,ignore_index=True)
vsz={i:sizes[i] for i in val_ids};res={}
for n,vs in CANDS.items():
    fv=fuse([view('val',val_ids,f'{DATA}/train/images',*v) for v in vs],vsz)
    print(n,end=' ');res[n]=evaluate(fv,gt_val)[0]
BEST=max(res,key=res.get);print('BEST',BEST,round(res[BEST],4),res)
test_ids=pd.read_csv(f'{DATA}/sample_submission.csv').image_id.tolist()
tsz2={i:Image.open(f'{DATA}/test/images/{i}.jpg').size for i in test_ids}
ft=fuse([view('test',test_ids,f'{DATA}/test/images',*v) for v in CANDS[BEST]],tsz2)
ft.to_parquet(f'{RUNS}/{TRUN}/test_pred_tta_{BEST}.parquet')
write_sub(ft,f'{RUNS}/{TRUN}/submission_tta_{BEST}.csv')
