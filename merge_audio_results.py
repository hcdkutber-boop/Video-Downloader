#!/usr/bin/env python3
import json
from pathlib import Path

segments=[]
for p in Path("audio-parts").glob("**/transcript.json"):
    data=json.loads(p.read_text(encoding="utf-8"))
    segments.extend(data.get("segments",[]))

segments.sort(key=lambda x:(x["start"],x["end"],x.get("part",0)))

# Remove near-duplicate boundary segments caused by overlap.
dedup=[]
for s in segments:
    text=" ".join(s.get("text","").split())
    if not text:
        continue
    duplicate=False
    for prev in dedup[-4:]:
        same_text=(" ".join(prev.get("text","").split()) == text)
        close=abs(prev["start"]-s["start"]) < 3.0 and abs(prev["end"]-s["end"]) < 3.0
        if same_text and close:
            duplicate=True
            break
    if not duplicate:
        dedup.append(s)

out=Path("audio-aggregate"); out.mkdir(exist_ok=True)
(out/"transcript_all.json").write_text(
    json.dumps({"segments":dedup},ensure_ascii=False,indent=2),encoding="utf-8")
with (out/"transcript_all.txt").open("w",encoding="utf-8") as h:
    for s in dedup:
        h.write(f"[{s['start']:8.2f} - {s['end']:8.2f}] {s['text']}\n")
print(f"merged {len(dedup)} segments")
