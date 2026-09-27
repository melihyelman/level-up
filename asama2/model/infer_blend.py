"""
Roketsan Level Up AI - final submission (public LB 0.79722)
3 YOLO26 models (COCO-pretrained, Ultralytics) -> per-model test-time augmentation -> weighted box fusion blend -> submission.csv

usage:
  python infer_blend.py --test_dir /path/to/images --weights ./weights --out predictions.csv
  (competition order: add --sample sample_submission.csv)
weights dir must contain: night_l1536.pt  carunder_m1280.pt  patch_m1280.pt
"""
import os,argparse,warnings,numpy as np,pandas as pd,cv2
warnings.filterwarnings("ignore")
from ultralytics import YOLO
import ultralytics.utils.nms as NMS
from ensemble_boxes import weighted_boxes_fusion

CLASSES=['car','van','truck','bus'];C2I={c:i for i,c in enumerate(CLASSES)}

# multi-label nms: one box may keep both car and van scores (+1.8 mAP50 on val vs single label)
_orig=NMS.non_max_suppression
NMS.non_max_suppression=lambda *a,**k:_orig(*a,**{**k,'multi_label':True})

# per model: file, base imgsz, tta views (zoom rel. to base, hflip, ultralytics augment), blend weight
MODELS=[
    # yolo26l, 1536, trained on "carunder" data, 8-view multi-zoom tta. val mAP50 0.8748 alone
    dict(name='night',file='night_l1536.pt',base=1536,w=3,
         views=[(1,0,0),(1,1,0),(1.1,0,0),(1.25,0,0),(1.75,0,0),(2.0,0,0),(1,0,1),(1.25,1,0)]),
    # yolo26m, 1280, carunder data, 3-view tta. val 0.8598
    dict(name='carunder',file='carunder_m1280.pt',base=1280,w=1,
         views=[(1,0,0),(1,1,0),(1.25,0,0)]),
    # yolo26m, 1280, van/truck/bus patch data, single view. val 0.8432
    dict(name='patch',file='patch_m1280.pt',base=1280,w=1,
         views=[(1,0,0)]),
]
VIEW_WBF_IOU=0.65     # fusing tta views of one model
BLEND_WBF_IOU=0.65    # fusing the 3 models (weights learned on 647 val imgs: 3/1/1 -> val 0.8806)
MIN_AREA=100          # px^2, smaller boxes can never match a >=200 px^2 gt at iou .5

def px(base,z):
    return int(round(base*z/32)*32)

def predict_view(model,paths,imgsz,flip,ultra,batch):
    out={}
    for s in range(0,len(paths),batch):
        chunk=paths[s:s+batch];ims=[cv2.imread(p) for p in chunk]
        src=[np.ascontiguousarray(im[:,::-1]) for im in ims] if flip else ims
        res=model.predict(src,imgsz=imgsz,conf=0.001,iou=0.6,max_det=1000,half=True,augment=bool(ultra),verbose=False,nms=True)
        for p,im,r in zip(chunk,ims,res):
            H,W=im.shape[:2];b=r.boxes;xy=b.xyxy.cpu().numpy().copy()
            if flip:
                xy[:,[0,2]]=W-xy[:,[2,0]]
            out[p]=((xy/np.array([W,H,W,H])).clip(0,1),b.conf.cpu().numpy(),b.cls.cpu().numpy())
    return out

def run_model(cfg,paths,wdir):
    model=YOLO(os.path.join(wdir,cfg['file']));views=[]
    for z,fl,ua in cfg['views']:
        print(cfg['name'],'view',px(cfg['base'],z),'flip' if fl else '','ultra' if ua else '',flush=True)
        views.append(predict_view(model,paths,px(cfg['base'],z),fl,ua,batch=max(1,int(8/z**2))))
    fused={}
    for p in paths:
        B=[v[p][0] for v in views];S=[v[p][1] for v in views];L=[v[p][2] for v in views]
        if len(views)==1:
            b,s,l=B[0],S[0],L[0]
        elif any(len(x) for x in S):
            b,s,l=weighted_boxes_fusion(B,S,L,iou_thr=VIEW_WBF_IOU,skip_box_thr=0.001,conf_type='avg')
        else:
            b,s,l=np.zeros((0,4)),np.zeros(0),np.zeros(0)
        fused[p]=(np.asarray(b),np.asarray(s),np.asarray(l))
    return fused

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--test_dir',required=True);ap.add_argument('--sample',default=None,help='optional, else all .jpg/.png in test_dir')
    ap.add_argument('--weights',default='weights');ap.add_argument('--out',default='submission.csv')
    a=ap.parse_args()
    if a.sample:
        sub=pd.read_csv(a.sample);ids=sub.image_id.tolist();paths=[os.path.join(a.test_dir,f'{i}.jpg') for i in ids]
    else:
        fs=sorted(f for f in os.listdir(a.test_dir) if f.lower().endswith(('.jpg','.jpeg','.png')))
        ids=[os.path.splitext(f)[0] for f in fs];paths=[os.path.join(a.test_dir,f) for f in fs];sub=pd.DataFrame({'image_id':ids})
    per_model=[run_model(cfg,paths,a.weights) for cfg in MODELS];wts=[cfg['w'] for cfg in MODELS]
    rows={}
    for i,p in zip(ids,paths):
        H,W=cv2.imread(p).shape[:2];B,S,L=[],[],[]
        for m in per_model:
            b,s,l=m[p]
            keep=(b[:,2]-b[:,0])*W*(b[:,3]-b[:,1])*H>=MIN_AREA if len(b) else np.zeros(0,bool)
            B.append(b[keep]);S.append(s[keep]);L.append(l[keep])
        if not any(len(x) for x in S):
            rows[i]='none';continue
        b,s,l=weighted_boxes_fusion(B,S,L,weights=wts,iou_thr=BLEND_WBF_IOU,skip_box_thr=0.0002,conf_type='avg')
        parts=[]
        for (x1,y1,x2,y2),c,k in zip(b,s,l):
            x,y,w,h=x1*W,y1*H,(x2-x1)*W,(y2-y1)*H
            if w*h>=MIN_AREA:
                parts.append(f'{CLASSES[int(k)]} {c:.5f} {x:.1f} {y:.1f} {w:.1f} {h:.1f}')
        rows[i]=' '.join(parts) if parts else 'none'
    sub['PredictionString']=sub.image_id.map(rows);sub.to_csv(a.out,index=False)
    print('wrote',a.out,len(sub),'rows, none:',(sub.PredictionString=='none').sum())

if __name__=='__main__':
    main()
