#!/usr/bin/env python3
import json, shutil
from pathlib import Path

root=Path(".")
out=Path("aggregate-output")
shutil.rmtree(out,ignore_errors=True)
(out/"candidates").mkdir(parents=True,exist_ok=True)
(out/"crops").mkdir(parents=True,exist_ok=True)

trans=[]
for p in root.glob("audio-parts/**/transcript.json"):
    data=json.loads(p.read_text(encoding="utf-8"))
    trans += data.get("segments",[])
trans.sort(key=lambda x:(x["start"],x["end"],x.get("part",0)))

vis=[]
for p in root.glob("visual-parts/**/manifest.json"):
    data=json.loads(p.read_text(encoding="utf-8"))
    part=int(data.get("part",0))
    srcdir=p.parent/"candidates"
    for x in data.get("candidates",[]):
        src=srcdir/x["file"]
        name=f"p{part:02d}_{x['file']}"
        dst=out/"candidates"/name
        if src.exists():
            shutil.copy2(src,dst)
        cropname=x.get("crop_file")
        agg_crop=None
        if cropname:
            cropsrc=p.parent/"crops"/cropname
            agg_crop=f"p{part:02d}_{cropname}"
            if cropsrc.exists():
                shutil.copy2(cropsrc,out/"crops"/agg_crop)
        y=dict(x); y["part"]=part; y["aggregate_file"]=name; y["aggregate_crop_file"]=agg_crop
        vis.append(y)
vis.sort(key=lambda x:x["time_sec"])

(out/"transcript_all.json").write_text(
    json.dumps({"segments":trans},ensure_ascii=False,indent=2),encoding="utf-8")
(out/"visual_candidates_all.json").write_text(
    json.dumps({"candidates":vis},ensure_ascii=False,indent=2),encoding="utf-8")

with (out/"transcript_all.txt").open("w",encoding="utf-8") as h:
    for s in trans:
        h.write(f"[{s['start']:8.2f}-{s['end']:8.2f}] {s['text']}\n")
