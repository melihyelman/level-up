# Experiments

One row per trained model or submission. Update after every run.

| # | run | model / imgsz / ep | data variant | val split | val mAP50 (ultra) | val mAP50 (ours) | per class car/van/truck/bus | LB public | notes |
|---|---|---|---|---|---|---|---|---|---|
| 01 | y26m_1280_base_40ep_randval | yolo26m / 1280 / 40 | base | **random** (old nb, incl 2000x1500) | 0.824 (ep35 best) | **0.797** raw, **0.808** w/ dup α=0.05 | 0.90 / **0.68** / 0.78 / 0.83 | **0.70531** (submission_cut200.csv) | old notebook: submission_cut200.csv (dup α 0.3 = 0.796 on val). plateau from ep ~27. van weakest: 21% of vans predicted car. recall <16px 62%. 200 cut costs only ~0.1pt |
| 01c | same model, multi-label NMS | – | – | – | – | **0.826** (val) | 0.91 / 0.75 / 0.80 / 0.86 | ? | submission_multilabel_nms06.csv: nms=True (one2many head), multi_label, iou 0.6, max_det 1000, min area 100, no dups. +1.8 vs e2e+dup |
| 01b | same model, new postprocess | – | – | – | – | 0.808 (val) | – | ? | submission_dup005_min100.csv: dup α 0.05, min area 100, iou 0.7 |

| 02 | rfdetr_m896 | rf-detr medium / 896 (trained at 1056 square) / 10 ep, 35 min | base | test-like | ema mAP50 0.801 (still rising ~+0.5/ep) | **0.805** (dup no gain) | .913/.700/.770/.830 (62 overlap imgs) | ? | files: runs/02_rfdetr_m896/{val_pred,test_pred_raw}.parquet, drive submission.csv + checkpoint_best_total.pth. capped at 300 boxes/img (num_select default). notebook roketsan_rfdetr.ipynb (drive id 1rBvFnkd2N0dgaetciNmyv6kGOrBpPp1b). RULE RISK: dinov2 + o365 pretrain |
| 02e | wbf yolo01 multilabel + rfdetr02 | – | – | 62 imgs unseen by both | – | **0.844** vs yolo alone 0.842 on same imgs (noise) | .924/.756/.827/.871 | ? | runs/02_rfdetr_m896/submission_wbf_yolo2_rfdetr1.csv: weights 2:1, iou 0.6, box_and_model_avg, min area 100. van +2.4, others ~same. RULE RISK (rfdetr). script analysis/ens_sub.py, grid in ens_log.txt
| 03 | p2_patch | yolo26m / 1280 / 20 nominal -> 15 real ep, 42 min | patch v2 (van1/truck2/bus3, cars grayed, 0 extra cars) | test-like | 0.842 (ep15, still rising) | **0.843** (multilabel nms) | .919 / .737 / .818 / **.900** | ? | notebook roketsan_patch.ipynb. drive roketsan_runs/p2_patch/submission.csv. local runs/03_p2_patch/{val_pred,test_pred_raw}.parquet |
| 03e | wbf p2_patch + rfdetr02 | – | – | test-like, 647 imgs | – | **0.849** (w5:1, iou .6, box_and_model_avg) | .923 / .743 / .825 / .906 | ? | runs/03_p2_patch/submission_wbf_patch5_rfdetr1.csv. 1:1 worse (0.840), gain grows w/ yolo weight then flat (3:1 .848, 4:1 .849). per-class weights no extra gain. RULE RISK (rfdetr) |
| 04 | p2_patch_clahe_e28 | yolo26m / 1280 / 28 nominal -> 20 real ep, ~55 min | patch v2 + clahe on dark imgs (train+val+test, patches too) | test-like | 0.843 (ep19-20 flat, 0.838 at ep15) | **0.843** (= p2_patch) | .920 / .737 / .817 / .899 | ? | user copy nb 1WTZQZ7fbchAx8GkjMI2vD0GVFPyCl-B9. +5 ep and clahe: no change overall. dark imgs (<50 gray, 72): 0.7633 -> 0.7634, clahe = no effect |
| 05 | p3_carunder_sh0.8_e20 | yolo26m / 1280 / 20 nominal -> 26 real ep, 43 min | drop 1537 imgs w/ car share >=.8 and no bus/truck (-25k cars, -2k vans in train), no aug, no patches | test-like | 0.846 (ep24) | **0.8446** (best single, +0.14 vs patch = noise) | .917 / .741 / .821 / .900 | ? | nb roketsan_carunder.ipynb. NO patches yet bus .900 = patch -> patch gain vs run01 was likely split difference, not patches |
| 04e | wbf p2_patch + p2_patch_clahe (yolo only) | – | – | test-like 647 | – | **0.8525** (1:1, iou .7, avg) | .924 / .749 / .831 / .906 | ? | +0.9 over single, no rule risk, beats yolo+rfdetr 0.849. next: add carunder (3 yolo) |
| 05t | carunder + TTA (base/flip/up 1.25x, wbf .65) | – | – | test-like 647 | – | **0.8598** (+1.5 vs 0.8446, best so far) | .927 / .761 / .842 / .909 | ? | drive p3_carunder_sh0.8_e20/submission_tta.csv (1 none row). no rule risk. every class up |
| 06 | wbf teammate yolo26m_1536_cont (LB 0.78126, own split + tta) + our carunder+tta | – | – | none (teammate trained on our val) | – | – | – | ? | runs/06_merge_teammate/submission_merge_team_carundertta_{1to1,team2to1,ours2to1}.csv, iou .7 avg. weights by LB only. submit 1to1 first |
| 07 | p4_carunder_yolo26l_1536_e30 (night run) | yolo26l / 1536 / 30 nominal -> 39 real ep, batch 8 (disconnect at ep17, resumed) | carunder 0.8 | test-like | – | **0.8528** plain, **0.8670** tta3 (BEST single) | tta: .928 / .774 / .850 / .916 | ? | drive p4_.../submission_tta.csv. +0.8 over carunder m1280 both plain and tta. multi-zoom tta cell pending |
| 07t | night l1536 + multi-zoom tta grid8 (1536,flip,1696,1920,2688,3072,ultralytics aug,flip1920) | – | – | test-like | – | **0.8748** (cur3 0.8669, grid6 0.8738, grid6_mild 0.8728) | .932 / .786 / .860 / .922 | ? | drive p4_.../submission_tta_grid8.csv, test_pred_tta_grid8.parquet. BEST overall, no rule risk |
| 08 | wbf teammate (LB .781) + night grid8 [+ carunder tta] | – | – | none (teammate saw our val) | – | – | – | ? | runs/06_merge_teammate/submission_merge_team_night_1to1.csv, ..._team_night_carunder_111.csv. iou .7 avg |
| 09 | BLEND (weights learned on 647 val): night l1536 grid8 x3 + carunder m1280 tta x1 + patch m1280 x1, wbf iou .65 avg | – | – | test-like | – | **0.8806** (+0.57 over night alone) | .936 / .792 / .866 / .928 | ? | runs/09_blend/submission_blend_safe.csv (+ _plus_teammate 50/50). rfdetr got weight 0 (no gain) -> no rule risk. patch_clahe would give 0.8803 w/ it, dropped (no test file) |
| – | LB submitted 2026-09-26 ~03:00: mergedOne.csv (teammate+carunder tta 1:1), detr.csv (patch+rfdetr 5:1) | | | | | | | ? | fill in LB scores |

- LB vs val gap ~9pt (val 0.796 for the same file). Likely test = different scenes/flights, val shares scenes with train -> val optimistic. Top team 0.767 (2026-09-25 20:49)

## Submission files (archive, all kept)
- 01 `runs/01_.../submission_cut200.csv` LB 0.70531 (submitted)
- 01b `runs/01_.../submission_dup005_min100.csv`, `submission_dup005_min150.csv`
- 01c `runs/01_.../submission_multilabel_nms06.csv` (best yolo, submit next)
- 02 drive `roketsan_runs/rfdetr_m896/submission.csv` (rfdetr alone)
- 02e `runs/02_rfdetr_m896/submission_wbf_yolo2_rfdetr1.csv` (ensemble)
- 03 drive `roketsan_runs/p2_patch/submission.csv` (best single, no rule risk)
- 03e `runs/03_p2_patch/submission_wbf_patch5_rfdetr1.csv` (patch + rfdetr, rule risk)
- 06 `runs/06_merge_teammate/submission_merge_team_carundertta_1to1.csv` (+ team2to1, ours2to1): teammate 0.781 + carunder tta
- 05t drive `roketsan_runs/p3_carunder_sh0.8_e20/submission_tta.csv` (carunder + TTA, val 0.8598, BEST, no rule risk)
- weights: yolo `runs/01_.../best.pt` + drive y26m_1280_base; rfdetr drive rfdetr_m896/checkpoint_best_total.pth

## Folder layout
- `data/`: competition data + zip
- `notebook/`: make_nb.py (source of truth) -> roketsan_yolo26.ipynb (uploaded to Drive)
- `runs/NN_name/`: best.pt, submission csv, `analysis/` (local re-eval scripts, logs, metrics)
- `reports/`: dataset audit page + stats
- `NOTES.md`: decisions and findings; `EXPERIMENTS.md`: this table

## Drive
- runs: MyDrive/roketsan_runs/<run>/ (weights, results.csv, plots)
- run 01: https://drive.google.com/drive/folders/1DUuxUZPn_edln8Tq5fAtfSWw7ynqekHb
