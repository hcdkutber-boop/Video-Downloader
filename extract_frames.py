#!/usr/bin/env python3
import json, subprocess, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REQ=json.loads((ROOT/"frames_request.json").read_text(encoding="utf-8"))
TMP=ROOT/".frames-tmp"
OUT=ROOT/"frames-output"

if TMP.exists(): shutil.rmtree(TMP)
if OUT.exists(): shutil.rmtree(OUT)
TMP.mkdir(); OUT.mkdir()

url=REQ["url"]; h=int(REQ.get("max_height",480))
template=str(TMP/"source.%(ext)s")
subprocess.run([
    "yt-dlp","--no-playlist","--merge-output-format","mp4","--remux-video","mp4",
    "-f",f"bv*[height<={h}]+ba/b[height<={h}]/b",
    "-o",template,url
],check=True)
videos=sorted(TMP.glob("source.*"))
if not videos: raise SystemExit("video not found")
video=videos[0]

manifest=[]
for i,item in enumerate(REQ["frames"],1):
    sec=float(item["time_sec"])
    label=item.get("label",f"slide_{i:02d}")
    out=OUT/f"{i:02d}_{int(sec):04d}s.jpg"
    subprocess.run([
        "ffmpeg","-y","-loglevel","error",
        "-ss",str(sec),"-i",str(video),
        "-frames:v","1","-q:v","2",str(out)
    ],check=True)
    manifest.append({"index":i,"time_sec":sec,"label":label,"file":out.name})

(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"extracted {len(manifest)} frames")
