#!/usr/bin/env python3
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
LOG = OUT / "attempts.log"


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
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Only absolute http/https URLs are accepted")
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


def run_ytdlp(url, max_height, mode):
    log("ENGINE yt-dlp: starting")
    if mode == "probe":
        proc = subprocess.run(
            ["yt-dlp", "--no-playlist", "--dump-single-json", url],
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
        }

    template = str(OUT / "%(title).150B [%(id)s].%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--newline",
        "--write-info-json",
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
        (OUT / "probe.json").write_text(
            json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"status": "success", "engine": "rutube-direct", "mode": "probe", **metadata}

    hls_candidates = [(n, u) for n, u in streams if ".m3u8" in u.lower()]
    if not hls_candidates:
        raise RuntimeError("RUTUBE fallback found streams, but no HLS m3u8 stream")

    # Prefer the explicitly named HLS/best-looking balancer, otherwise first m3u8.
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
        "ffmpeg",
        "-y",
        "-loglevel",
        "warning",
        "-user_agent",
        UA,
        "-headers",
        headers,
        "-i",
        stream_url,
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
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

    if rutube_id(url):
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
