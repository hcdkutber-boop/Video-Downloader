# Video Downloader

Remote video-download tool operated through GitHub Actions.

## Flow

1. Edit `request.json`.
2. A GitHub Actions workflow runs automatically.
3. The runner downloads/probes the public video URL.
4. `result.json`, logs, metadata, and the downloaded media are published as a workflow artifact.

Primary engine: current yt-dlp from upstream master.
RUTUBE fallback: direct public metadata/play-options API + HLS/FFmpeg.

This repository is an execution tool, not an Android application.
