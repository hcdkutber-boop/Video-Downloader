#!/usr/bin/env python3
import json, os
from pathlib import Path
root=Path(".")
trans=[]
for p in root.glob("audio-parts/**/transcript.json"):
    trans += json.loads(p.read_text(encoding="utf-8")).get("segments",[])
trans.sort(key=lambda x:(x["start"],x["end"],x.get("part",0)))
vis=[]
for p in root.glob("visual-parts/**/manifest.json"):
    data=json.loads(p.read_text(encoding="utf-8"))
    for x in data.get("candidates",[]):
        y=dict(x); y["part"]=data.get("part"); vis.append(y)
vis.sort(key=lambda x:x["time_sec"])
out=Path("aggregate-output"); out.mkdir(exist_ok=True)
(out/"transcript_all.json").write_text(json.dumps({"segments":trans},ensure_ascii=False,indent=2),encoding="utf-8")
(out/"visual_candidates_all.json").write_text(json.dumps({"candidates":vis},ensure_ascii=False,indent=2),encoding="utf-8")
