#!/usr/bin/env python3
import argparse, json, math, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def run(cmd):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True)

def tc(sec):
    sec=max(0,float(sec)); h=int(sec//3600); m=int((sec%3600)//60); s=sec%60
    return f"{h:02d}:{m:02d}:{s:06.3f}"

def bounds(duration, parts, idx, overlap):
    base=duration/parts
    core_start=idx*base
    core_end=duration if idx==parts-1 else (idx+1)*base
    return max(0,core_start-overlap), min(duration,core_end+overlap), core_start, core_end

def download_section(url, start, end, max_height, outdir, audio_only=False):
    outdir.mkdir(parents=True, exist_ok=True)
    templ=str(outdir/"source.%(ext)s")
    section=f"*{tc(start)}-{tc(end)}"
    if audio_only:
        fmt="ba/b"
    else:
        h=int(max_height)
        fmt=f"bv*[height<={h}]+ba/b[height<={h}]/b"
    cmd=[
        "yt-dlp","--no-playlist","--download-sections",section,
        "--force-keyframes-at-cuts","-f",fmt,"-o",templ,url
    ]
    if not audio_only:
        cmd += ["--merge-output-format","mp4","--remux-video","mp4"]
    run(cmd)
    files=sorted([p for p in outdir.glob("source.*") if p.is_file()])
    if not files: raise RuntimeError("section download produced no file")
    return files[0]

def font(size=18):
    from PIL import ImageFont
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"]:
        if Path(p).exists(): return ImageFont.truetype(p,size)
    return ImageFont.load_default()

def make_contact_sheet(frames, abs_times, out):
    from PIL import Image, ImageDraw
    cols=4; cell_w=427; cell_h=240; label_h=28
    rows=math.ceil(len(frames)/cols)
    canvas=Image.new("RGB",(cols*cell_w,rows*(cell_h+label_h)),"white")
    d=ImageDraw.Draw(canvas); f=font(16)
    for i,(p,t) in enumerate(zip(frames,abs_times)):
        im=Image.open(p).convert("RGB")
        im.thumbnail((cell_w,cell_h))
        x=(i%cols)*cell_w; y=(i//cols)*(cell_h+label_h)
        canvas.paste(im,(x+(cell_w-im.width)//2,y+(cell_h-im.height)//2))
        d.text((x+7,y+cell_h+4),tc(t),fill="black",font=f)
    canvas.save(out,quality=90,optimize=True)

def probe(req, idx):
    parts=int(req.get("probe_parts",5))
    duration=float(req.get("probe_duration_sec",600))
    overlap=float(req.get("probe_overlap_sec",2))
    start,end,core_start,core_end=bounds(duration,parts,idx,overlap)
    out=ROOT/"probe-output"/f"part_{idx:02d}"
    tmp=ROOT/".parallel-tmp"/f"probe_{idx:02d}"
    shutil.rmtree(out,ignore_errors=True); shutil.rmtree(tmp,ignore_errors=True)
    out.mkdir(parents=True); tmp.mkdir(parents=True)
    vid=download_section(req["url"],start,end,req.get("max_height",480),tmp,False)
    interval=float(req.get("probe_frame_interval_sec",10))
    framesdir=out/"frames"; framesdir.mkdir()
    run(["ffmpeg","-y","-loglevel","error","-i",str(vid),
         "-vf",f"fps=1/{interval}","-q:v","2",str(framesdir/"frame_%03d.jpg")])
    frames=sorted(framesdir.glob("*.jpg"))
    abs_times=[start+i*interval for i in range(len(frames))]
    make_contact_sheet(frames,abs_times,out/"contact_sheet.jpg")
    (out/"manifest.json").write_text(json.dumps({
        "part":idx,"download_start":start,"download_end":end,
        "core_start":core_start,"core_end":core_end,
        "frames":[{"file":p.name,"time_sec":round(t,3)} for p,t in zip(frames,abs_times)]
    },ensure_ascii=False,indent=2),encoding="utf-8")

def crop_filter(c):
    return f"crop={int(c['w'])}:{int(c['h'])}:{int(c['x'])}:{int(c['y'])}"

def visual(req, idx):
    from PIL import Image, ImageChops, ImageStat
    parts=int(req.get("main_parts",15)); duration=float(req["duration_sec"])
    overlap=float(req.get("main_overlap_sec",4))
    start,end,core_start,core_end=bounds(duration,parts,idx,overlap)
    out=ROOT/"visual-output"/f"part_{idx:02d}"
    tmp=ROOT/".parallel-tmp"/f"visual_{idx:02d}"
    shutil.rmtree(out,ignore_errors=True); shutil.rmtree(tmp,ignore_errors=True)
    out.mkdir(parents=True); tmp.mkdir(parents=True)
    vid=download_section(req["url"],start,end,req.get("max_height",480),tmp,False)
    interval=float(req.get("visual_frame_interval_sec",1))
    raw=tmp/"raw"; raw.mkdir()
    run(["ffmpeg","-y","-loglevel","error","-i",str(vid),
         "-vf",f"fps=1/{interval}","-q:v","2",str(raw/"frame_%05d.jpg")])
    files=sorted(raw.glob("*.jpg"))
    cand=out/"candidates"; cand.mkdir()
    crops=out/"crops"; crops.mkdir()
    threshold=float(req.get("visual_change_threshold",1.2))
    heartbeat=float(req.get("visual_heartbeat_sec",20))
    min_gap=float(req.get("candidate_min_gap_sec",1))
    last_small=None; last_saved_t=-1e9; rows=[]
    for i,p in enumerate(files):
        abs_t=start+i*interval
        if abs_t < core_start-0.05 or abs_t > core_end+0.05:
            continue
        full=Image.open(p).convert("RGB")
        cr=req["crop"]
        crop=full.crop((int(cr["x"]),int(cr["y"]),int(cr["x"]+cr["w"]),int(cr["y"]+cr["h"])))
        im=crop.convert("L").resize((96,54))
        score=999.0 if last_small is None else ImageStat.Stat(ImageChops.difference(im,last_small)).mean[0]
        due=(abs_t-last_saved_t)>=heartbeat
        changed=(score>=threshold and (abs_t-last_saved_t)>=min_gap)
        if last_small is None or changed or due:
            dst=cand/f"{len(rows)+1:04d}_{int(abs_t):04d}s.jpg"
            cropdst=crops/f"{len(rows)+1:04d}_{int(abs_t):04d}s.jpg"
            shutil.copy2(p,dst)
            crop.save(cropdst,quality=94,optimize=True)
            rows.append({"file":dst.name,"crop_file":cropdst.name,"time_sec":round(abs_t,3),"diff_score":round(score,3)})
            last_saved_t=abs_t
        last_small=im
    (out/"manifest.json").write_text(json.dumps({
        "part":idx,"download_start":start,"download_end":end,
        "core_start":core_start,"core_end":core_end,"candidates":rows
    },ensure_ascii=False,indent=2),encoding="utf-8")

def audio(req, idx):
    from faster_whisper import WhisperModel
    parts=int(req.get("main_parts",15)); duration=float(req["duration_sec"])
    overlap=float(req.get("main_overlap_sec",4))
    start,end,core_start,core_end=bounds(duration,parts,idx,overlap)
    out=ROOT/"audio-output"/f"part_{idx:02d}"
    tmp=ROOT/".parallel-tmp"/f"audio_{idx:02d}"
    shutil.rmtree(out,ignore_errors=True); shutil.rmtree(tmp,ignore_errors=True)
    out.mkdir(parents=True); tmp.mkdir(parents=True)
    src=download_section(req["url"],start,end,req.get("max_height",480),tmp,True)
    wav=tmp/"audio.wav"
    run(["ffmpeg","-y","-loglevel","error","-i",str(src),"-vn","-ac","1","-ar","16000",
         "-c:a","pcm_s16le",str(wav)])
    model=WhisperModel(req.get("whisper_model","small"),device="cpu",compute_type="int8")
    segs,info=model.transcribe(str(wav),language=req.get("language","ru"),vad_filter=True,beam_size=5)
    rows=[]
    for s in segs:
        a=start+s.start; b=start+s.end
        if b < core_start or a > core_end: continue
        rows.append({"start":round(a,2),"end":round(b,2),"text":s.text.strip(),"part":idx})
        print(f"[{a:.2f}-{b:.2f}] {s.text.strip()}",flush=True)
    (out/"transcript.json").write_text(json.dumps({
        "part":idx,"language":info.language,"segments":rows
    },ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=["probe","visual","audio"])
    ap.add_argument("request")
    ap.add_argument("part",type=int)
    args=ap.parse_args()
    req=json.loads((ROOT/args.request).read_text(encoding="utf-8"))
    {"probe":probe,"visual":visual,"audio":audio}[args.mode](req,args.part)

if __name__=="__main__": main()
