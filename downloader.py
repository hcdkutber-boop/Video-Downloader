#!/usr/bin/env python3
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
LOG = OUT / "attempts.log"

INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://yewtu.be",
    "https://invidious.nerdvpn.de",
    "https://inv.us.projectsegfau.lt",
    "https://invidious.fdn.fr",
    "https://vid.puffyan.us",
    "https://iv.datura.network",
]


def log(message):
    message = str(message)
    print(message, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def write_result(data):
    data["finished_at_unix"] = int(time.time())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def safe_public_url(url):
    if isinstance(url, str) and (re.fullmatch(r"ytsearch\d*:.+", url, re.I) or url.lower().startswith("rutubesearch:")):
        return url
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Only absolute http/https URLs or ytsearchN: queries are accepted")
    host = p.hostname.lower()
    if host in ("localhost",) or host.endswith(".local"):
        raise ValueError("Local hosts are not accepted")
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", host):
        raise ValueError("Literal IP addresses are not accepted")
    return url


def rutube_id(url):
    m = re.search(
        r"https?://(?:www\.)?rutube\.ru/(?:(?:live/)?video(?:/private)?|(?:play/)?embed)/([0-9a-z]{32})",
        url,
        re.I,
    )
    return m.group(1) if m else None


def youtube_id(url):
    if not isinstance(url, str):
        return None
    if url.startswith("ytsearch"):
        return None
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        m = re.match(r"/([A-Za-z0-9_-]{11})", p.path)
        return m.group(1) if m else None
    if host.endswith("youtube.com"):
        qs = parse_qs(p.query)
        if "v" in qs and qs["v"]:
            vid = qs["v"][0]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                return vid
        m = re.search(r"/(?:embed|shorts)/([A-Za-z0-9_-]{11})", p.path)
        return m.group(1) if m else None
    return None


def clean_name(value, limit=150):
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", value or "video")
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:limit] or "video"


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def media_result(path, engine, extra=None):
    result = {
        "status": "success",
        "engine": engine,
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if extra:
        result.update(extra)
    return result


def quality_selector(max_height):
    if not max_height:
        return "bv*+ba/b"
    h = int(max_height)
    return f"bv*[height<={h}]+ba/b[height<={h}]/b"


def ytdlp_common_args():
    return [
        "--user-agent", UA,
        "--extractor-args", "youtube:player_client=android,ios,web_embedded;player_skip=webpage",
    ]


def run_ytdlp(url, max_height, mode):
    log("ENGINE yt-dlp: starting")
    if mode == "probe":
        proc = subprocess.run(
            ["yt-dlp", *ytdlp_common_args(), "--no-playlist", "--dump-single-json", url],
            text=True,
            capture_output=True,
        )
        if proc.stderr:
            log(proc.stderr[-12000:])
        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp probe failed with code {proc.returncode}")
        info = json.loads(proc.stdout)
        (OUT / "probe.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "status": "success",
            "engine": "yt-dlp",
            "mode": "probe",
            "id": info.get("id"),
            "title": info.get("title"),
            "duration": info.get("duration"),
            "extractor": info.get("extractor"),
            "webpage_url": info.get("webpage_url"),
        }

    template = str(OUT / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        *ytdlp_common_args(),
        "--no-playlist",
        "--newline",
        "--write-info-json",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs",
        "ru.*,ru,en.*",
        "--sub-format",
        "vtt/best",
        "--merge-output-format",
        "mp4",
        "--remux-video",
        "mp4",
        "--print",
        "after_move:filepath",
        "-f",
        quality_selector(max_height),
        "-o",
        template,
        url,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.stdout:
        log(proc.stdout[-12000:])
    if proc.stderr:
        log(proc.stderr[-12000:])
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed with code {proc.returncode}")

    candidates = sorted(
        [p for p in OUT.iterdir() if p.is_file() and p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("yt-dlp reported success but no media file was found")

    path = candidates[0]
    info_files = sorted(OUT.glob("*.info.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    extra = {}
    if info_files:
        try:
            info = json.loads(info_files[0].read_text(encoding="utf-8"))
            extra = {
                "id": info.get("id"),
                "title": info.get("title"),
                "duration": info.get("duration"),
                "extractor": info.get("extractor"),
                "webpage_url": info.get("webpage_url"),
            }
        except Exception as e:
            log(f"Metadata parse warning: {e}")
    return media_result(path, "yt-dlp", extra)


def get_json(url):
    r = requests.get(
        url,
        headers={
            "User-Agent": UA,
            "Referer": "https://rutube.ru/",
            "Origin": "https://rutube.ru",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def pick_height(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    m = re.search(r"(\d+)", str(value))
    return int(m.group(1)) if m else 0


def get_invidious_info(video_id):
    last_error = None
    for base in INVIDIOUS_INSTANCES:
        url = f"{base.rstrip('/')}/api/v1/videos/{video_id}"
        try:
            log(f"ENGINE invidious: probing {base}")
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            if r.status_code != 200:
                last_error = f"{base}: HTTP {r.status_code}"
                continue
            data = r.json()
            if data.get("error"):
                last_error = f"{base}: {data.get('error')}"
                continue
            data["_invidious_instance"] = base
            return data
        except Exception as e:
            last_error = f"{base}: {type(e).__name__}: {e}"
            continue
    raise RuntimeError(f"all Invidious instances failed; last={last_error}")


def run_youtube_invidious_fallback(url, max_height, mode):
    vid = youtube_id(url)
    if not vid:
        raise RuntimeError("YouTube fallback cannot extract video id")
    info = get_invidious_info(vid)
    title = info.get("title") or vid
    duration = int(info.get("lengthSeconds") or 0) or None
    instance = info.get("_invidious_instance")

    (OUT / "probe.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {
        "id": vid,
        "title": title,
        "duration": duration,
        "extractor": "youtube-invidious",
        "webpage_url": f"https://www.youtube.com/watch?v={vid}",
        "invidious_instance": instance,
    }
    if mode == "probe":
        return {"status": "success", "engine": "youtube-invidious", "mode": "probe", **metadata}

    hmax = int(max_height or 1080)
    combined = []
    for f in info.get("formatStreams") or []:
        height = pick_height(f.get("height") or f.get("qualityLabel"))
        stream_url = f.get("url")
        container = (f.get("container") or f.get("type") or "").lower()
        if stream_url and height and height <= hmax and ("mp4" in container or not container):
            combined.append((height, int(f.get("bitrate") or 0), stream_url, f))
    if combined:
        combined.sort(key=lambda x: (x[0], x[1]), reverse=True)
        height, _, stream_url, fmt = combined[0]
        output = OUT / f"{clean_name(title)} [{vid}].mp4"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "warning",
            "-user_agent", UA,
            "-i", stream_url,
            "-c", "copy",
            "-movflags", "+faststart",
            str(output),
        ]
        log(f"ENGINE invidious: downloading combined height={height}")
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.stdout:
            log(proc.stdout[-12000:])
        if proc.stderr:
            log(proc.stderr[-12000:])
        if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
            return media_result(output, "youtube-invidious", {**metadata, "selected_height": height, "mode": "combined"})
        log(f"Combined format failed with code {proc.returncode}; trying adaptive")

    videos = []
    audios = []
    for f in info.get("adaptiveFormats") or []:
        stream_url = f.get("url")
        mime = (f.get("type") or f.get("mimeType") or "").lower()
        height = pick_height(f.get("height") or f.get("qualityLabel"))
        bitrate = int(f.get("bitrate") or 0)
        if not stream_url:
            continue
        if "video/mp4" in mime and height and height <= hmax:
            videos.append((height, bitrate, stream_url, f))
        if "audio/mp4" in mime or "audio/webm" in mime or (not height and "audio" in mime):
            audios.append((bitrate, stream_url, f))
    if not videos or not audios:
        raise RuntimeError("Invidious returned no usable combined or adaptive mp4/audio streams")
    videos.sort(key=lambda x: (x[0], x[1]), reverse=True)
    audios.sort(key=lambda x: x[0], reverse=True)
    height, _, video_url, _ = videos[0]
    _, audio_url, _ = audios[0]
    output = OUT / f"{clean_name(title)} [{vid}].mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-user_agent", UA,
        "-i", video_url,
        "-user_agent", UA,
        "-i", audio_url,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c", "copy",
        "-movflags", "+faststart",
        str(output),
    ]
    log(f"ENGINE invidious: downloading adaptive height={height}")
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.stdout:
        log(proc.stdout[-12000:])
    if proc.stderr:
        log(proc.stderr[-12000:])
    if proc.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg YouTube/Invidious fallback failed with code {proc.returncode}")
    return media_result(output, "youtube-invidious", {**metadata, "selected_height": height, "mode": "adaptive"})


def run_rutube_search(search_url, max_height, mode):
    query = search_url.split(":", 1)[1]
    endpoints = [
        "https://rutube.ru/api/search/video/",
        "https://rutube.ru/api/search/",
    ]
    results = []
    last_error = None
    for endpoint in endpoints:
        try:
            log(f"ENGINE rutube-search: {endpoint} q={query}")
            r = requests.get(endpoint, params={"query": query}, headers={"User-Agent": UA, "Referer": "https://rutube.ru/"}, timeout=30)
            log(f"rutube-search HTTP {r.status_code} {r.url}")
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                continue
            data = r.json()
            (OUT / "rutube_search.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            raw_results = data.get("results") or data.get("items") or []
            for item in raw_results:
                title = item.get("title") or item.get("name") or ""
                video_url = item.get("video_url") or item.get("url") or item.get("html_url") or item.get("link")
                video_id = item.get("id") or item.get("video_id")
                if not video_url and isinstance(video_id, str) and re.fullmatch(r"[0-9a-f]{32}", video_id):
                    video_url = f"https://rutube.ru/video/{video_id}/"
                results.append({"title": title, "url": video_url, "id": video_id, "raw": item})
            if results:
                break
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            log(f"rutube-search error: {last_error}")
    if not results:
        raise RuntimeError(f"rutube search found no results; last={last_error}")

    chosen = None
    for item in results:
        title_l = (item.get("title") or "").lower()
        if "автостат оперативка" in title_l and "сентябр" in title_l and "2026" in title_l:
            chosen = item
            break
    if not chosen:
        for item in results:
            title_l = (item.get("title") or "").lower()
            if "автостат оперативка" in title_l:
                chosen = item
                break
    if not chosen:
        chosen = results[0]

    (OUT / "rutube_search_selected.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=2), encoding="utf-8")
    selected_url = chosen.get("url")
    if not selected_url:
        raise RuntimeError(f"rutube search selected result has no URL: {chosen.get('title')}")
    if mode == "probe":
        return {"status": "success", "engine": "rutube-search", "mode": "probe", "title": chosen.get("title"), "webpage_url": selected_url, "results_count": len(results)}
    log(f"rutube-search selected: {chosen.get('title')} -> {selected_url}")
    return run_rutube_fallback(selected_url, max_height, mode)


def choose_hls_variant(master_url, max_height):
    r = requests.get(
        master_url,
        headers={"User-Agent": UA, "Referer": "https://rutube.ru/"},
        timeout=30,
    )
    r.raise_for_status()
    text = r.text
    if "#EXT-X-STREAM-INF" not in text:
        return master_url, None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    variants = []
    for i, line in enumerate(lines[:-1]):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        attrs = line.split(":", 1)[1]
        next_line = lines[i + 1]
        if next_line.startswith("#"):
            continue
        hm = re.search(r"RESOLUTION=\d+x(\d+)", attrs)
        bm = re.search(r"BANDWIDTH=(\d+)", attrs)
        height = int(hm.group(1)) if hm else 0
        bandwidth = int(bm.group(1)) if bm else 0
        variants.append((height, bandwidth, urljoin(master_url, next_line)))

    if not variants:
        return master_url, None

    if max_height:
        eligible = [v for v in variants if not v[0] or v[0] <= int(max_height)]
        if eligible:
            variants = eligible

    chosen = max(variants, key=lambda v: (v[0], v[1]))
    return chosen[2], chosen[0] or None


def run_rutube_fallback(url, max_height, mode):
    video_id = rutube_id(url)
    if not video_id:
        raise RuntimeError("RUTUBE fallback cannot extract a 32-character video id")

    log(f"ENGINE rutube-direct: video id {video_id}")
    info = get_json(f"https://rutube.ru/api/video/{video_id}/?format=json")
    options = get_json(f"https://rutube.ru/api/play/options/{video_id}/?format=json")

    balancer = options.get("video_balancer") or {}
    if not isinstance(balancer, dict) or not balancer:
        raise RuntimeError("RUTUBE play/options returned no video_balancer")

    streams = [
        (name, value)
        for name, value in balancer.items()
        if isinstance(value, str) and value.startswith(("http://", "https://"))
    ]
    if not streams:
        raise RuntimeError("RUTUBE returned no usable stream URLs")

    metadata = {
        "id": video_id,
        "title": info.get("title"),
        "duration": info.get("duration"),
        "uploader": (info.get("author") or {}).get("name") if isinstance(info.get("author"), dict) else None,
        "available_balancers": [name for name, _ in streams],
    }

    if mode == "probe":
        probe = {"info": info, "options": options}
        (OUT / "probe.json").write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "success", "engine": "rutube-direct", "mode": "probe", **metadata}

    hls_candidates = [(n, u) for n, u in streams if ".m3u8" in u.lower()]
    if not hls_candidates:
        raise RuntimeError("RUTUBE fallback found streams, but no HLS m3u8 stream")

    hls_candidates.sort(
        key=lambda item: (
            "hls" in item[0].lower(),
            "m3u8" in item[0].lower(),
            "1080" in item[0],
        ),
        reverse=True,
    )
    balancer_name, master_url = hls_candidates[0]
    stream_url, selected_height = choose_hls_variant(master_url, max_height)
    log(f"RUTUBE HLS balancer={balancer_name}, selected_height={selected_height or 'auto'}")

    filename = clean_name(info.get("title") or f"rutube-{video_id}")
    output = OUT / f"{filename} [{video_id}].mp4"
    headers = "Referer: https://rutube.ru/\r\nOrigin: https://rutube.ru\r\n"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-user_agent", UA,
        "-headers", headers,
        "-i", stream_url,
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c", "copy",
        "-movflags", "+faststart",
        str(output),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.stdout:
        log(proc.stdout[-12000:])
    if proc.stderr:
        log(proc.stderr[-12000:])
    if proc.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg RUTUBE fallback failed with code {proc.returncode}")

    (OUT / f"{video_id}.rutube-info.json").write_text(
        json.dumps({"info": info, "options": options}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    metadata["selected_height"] = selected_height
    metadata["balancer"] = balancer_name
    return media_result(output, "rutube-direct", metadata)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: downloader.py request.json")

    request_path = Path(sys.argv[1])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    url = safe_public_url(request["url"])
    mode = request.get("mode", "download")
    if mode not in ("download", "probe"):
        raise ValueError("mode must be download or probe")
    max_height = request.get("max_height", 1080)
    request_id = str(request.get("request_id") or int(time.time()))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    base = {
        "request_id": request_id,
        "url": url,
        "mode": mode,
        "max_height": max_height,
        "started_at_unix": int(time.time()),
    }

    errors = []
    try:
        result = run_ytdlp(url, max_height, mode)
        write_result({**base, **result})
        return 0
    except Exception as e:
        msg = f"yt-dlp failed: {type(e).__name__}: {e}"
        errors.append(msg)
        log(msg)

    if isinstance(url, str) and url.lower().startswith("rutubesearch:"):
        try:
            result = run_rutube_search(url, max_height, mode)
            result["previous_errors"] = errors
            write_result({**base, **result})
            return 0
        except Exception as e:
            msg = f"rutube-search failed: {type(e).__name__}: {e}"
            errors.append(msg)
            log(msg)

    if isinstance(url, str) and youtube_id(url):
        try:
            result = run_youtube_invidious_fallback(url, max_height, mode)
            result["previous_errors"] = errors
            write_result({**base, **result})
            return 0
        except Exception as e:
            msg = f"youtube-invidious failed: {type(e).__name__}: {e}"
            errors.append(msg)
            log(msg)

    if isinstance(url, str) and rutube_id(url):
        try:
            result = run_rutube_fallback(url, max_height, mode)
            result["previous_errors"] = errors
            write_result({**base, **result})
            return 0
        except Exception as e:
            msg = f"rutube-direct failed: {type(e).__name__}: {e}"
            errors.append(msg)
            log(msg)

    write_result({**base, "status": "failed", "errors": errors})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
