#!/usr/bin/env python3
import json, math, os, shutil, subprocess, sys, time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "review-output"
TMP = ROOT / ".review-tmp"

def run(cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=True, **kw)

def load_request():
    return json.loads((ROOT / "review_request.json").read_text(encoding="utf-8"))

def download_video(url, max_height=480):
    TMP.mkdir(exist_ok=True)
    template = str(TMP / "source.%(ext)s")
    h = int(max_height or 480)
    run([
        "yt-dlp","--no-playlist","--merge-output-format","mp4",
        "--remux-video","mp4","-f",f"bv*[height<={h}]+ba/b[height<={h}]/b",
        "-o",template,url
    ])
    vids = sorted(TMP.glob("source.*"))
    if not vids:
        raise RuntimeError("No downloaded video found")
    return vids[0]

def extract_frames(video, interval):
    frames = TMP / "frames"
    frames.mkdir(exist_ok=True)
    run([
        "ffmpeg","-y","-loglevel","error","-i",str(video),
        "-vf",f"fps=1/{interval},scale=960:-2",
        "-q:v","3",str(frames/"frame_%05d.jpg")
    ])
    return sorted(frames.glob("frame_*.jpg"))

def font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def make_sheets(frames, interval):
    sheets = OUT / "contact_sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    cols, rows = 4, 3
    thumb_w, thumb_h = 480, 270
    label_h = 30
    per = cols*rows
    fnt = font(18)
    manifest=[]
    for si in range(math.ceil(len(frames)/per)):
        chunk = frames[si*per:(si+1)*per]
        canvas = Image.new("RGB",(cols*thumb_w,rows*(thumb_h+label_h)),"white")
        draw = ImageDraw.Draw(canvas)
        entries=[]
        for j,p in enumerate(chunk):
            idx=si*per+j
            sec=idx*interval
            im=Image.open(p).convert("RGB")
            im.thumbnail((thumb_w,thumb_h))
            x=(j%cols)*thumb_w
            y=(j//cols)*(thumb_h+label_h)
            canvas.paste(im,(x+(thumb_w-im.width)//2,y+(thumb_h-im.height)//2))
            hh=sec//3600; mm=(sec%3600)//60; ss=sec%60
            label=f"{hh:02d}:{mm:02d}:{ss:02d}"
            draw.rectangle((x,y+thumb_h,x+thumb_w,y+thumb_h+label_h),fill="white")
            draw.text((x+8,y+thumb_h+5),label,fill="black",font=fnt)
            entries.append({"frame":p.name,"time_sec":sec,"timecode":label})
        out=sheets/f"sheet_{si+1:03d}.jpg"
        canvas.save(out,quality=88,optimize=True)
        manifest.append({"sheet":out.name,"entries":entries})
    (OUT/"frames_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")

def extract_audio(video):
    audio=TMP/"audio.wav"
    run(["ffmpeg","-y","-loglevel","error","-i",str(video),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio)])
    return audio

def transcribe(audio):
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio), language="ru", vad_filter=True, beam_size=5)
    rows=[]
    txt=[]
    for s in segments:
        row={"start":round(s.start,2),"end":round(s.end,2),"text":s.text.strip()}
        rows.append(row)
        txt.append(f"[{s.start:8.2f} - {s.end:8.2f}] {s.text.strip()}")
        print(txt[-1], flush=True)
    (OUT/"transcript.json").write_text(json.dumps({"language":info.language,"segments":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"transcript.txt").write_text("\n".join(txt),encoding="utf-8")

def main():
    req=load_request()
    interval=int(req.get("frame_interval_sec",5))
    if OUT.exists():
        shutil.rmtree(OUT)
    if TMP.exists():
        shutil.rmtree(TMP)
    OUT.mkdir(parents=True)
    TMP.mkdir(parents=True)
    video=download_video(req["url"], req.get("max_height", 480))
    frames=extract_frames(video,interval)
    make_sheets(frames,interval)
    audio=extract_audio(video)
    transcribe(audio)
    summary={
        "url":req["url"],
        "frame_interval_sec":interval,
        "frame_count":len(frames),
        "contact_sheet_count":len(list((OUT/"contact_sheets").glob("*.jpg"))),
        "generated_at_unix":int(time.time())
    }
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
