# AUTOSTAT Operativka — September 2026 (9 months) — DELIVERED

**Final status (2026-10-08): CHECKED + SENT via Gmail. No repeat search, download, processing, or sending is required for this month.**

## Authoritative methodology v1.0
- Google Drive: https://docs.google.com/document/d/1gZI5bP2zfV05M0cXm5W4VIVAtGdRtvs_tHrmBNHSF8o/edit
- GitHub: https://github.com/hcdkutber-boop/Video-Downloader/blob/main/VIDEO_TO_PRESENTATION_ALGORITHM.md
- Repository: https://github.com/hcdkutber-boop/Video-Downloader

## Video source
- September 2026 AUTOSTAT Operativka at CarX'26 held on 2026-10-06.
- Accessible complete VK archive: https://vk.com/video-25815680_456239132, metadata 2582s / 43:02 including stage pre-roll and discussion.
- YouTube: https://www.youtube.com/watch?v=ZtAOFHAqOmk, blocked for download from GitHub Actions by YouTube bot challenge. Prefer verified VK source on future processing.
- Correct VK host for yt-dlp: `vk.com/video-25815680_456239132`. `vkvideo.ru/live-...` redirects to `badbrowser.php` and is unsuitable.

## Verified GitHub Actions checkpoints
1. VK direct-link metadata: https://github.com/hcdkutber-boop/Video-Downloader/actions/runs/37821539580 — success.
2. 5-way initial 00:00–10:00 video probe: https://github.com/hcdkutber-boop/Video-Downloader/actions/runs/37821669043 — all five success; pre-roll splash screen.
3. 5-way content probe 13:00–23:00: https://github.com/hcdkutber-boop/Video-Downloader/actions/runs/37822148095 — all five success; AUTOSTAT presentation starts around 19 min.
4. Main visual+audio job: https://github.com/hcdkutber-boop/Video-Downloader/actions/runs/37822887840 — 15 visual parts success; audio jobs initially failed due to PyAV 19 / faster-whisper compatibility.
5. Audio-only recovery: https://github.com/hcdkutber-boop/Video-Downloader/actions/runs/37823372651 — all 15 audio transcriptions and aggregate success. Code fixed to read ffmpeg-produced 16kHz PCM WAV to float32 NumPy array before Whisper inference.
6. 542 image candidates collected, deduplicated/filtered to 15 distinct original screenshot slides; no contact-sheet thumbnails used in PPTX. Some native composite video frames cropped to show only the original slide (no redraw).
7. DOCX assembled from verified frames and transcript with slide-by-slide absolute display time intervals. 17 rendered pages. PPTX 15 slides. Both ZIP/OOXML containers tested and rendered successfully for visual QA.

## Final deliverables
- `AUTOSTAT_Operativka_September_2026_original_slides.pptx` — 15 slides, 2,660,011 bytes.
- `AUTOSTAT_Operativka_September_2026_notes_by_slides.docx` — 17 pages, 2,663,445 bytes.
- Created and inspected on 2026-10-08. Both were attached to Gmail message.
- Gmail **Sent** message ID `1a11cc987c4e54c3`, subject `АВТОСТАТ Оперативка — сентябрь 2026`, to `vchernyadyev@alfabank.ru` and `hcdkutber@yandex.ru`. Search after sending confirmed both attachments and both recipients, with SENT label.

## Lessons for future months
- First read the methodology v1.0; inspect prior run IDs/artifacts and month checkpoint, avoid unnecessary repeated discovery.
- Source discovery and delivery status are separate phases.
- Use direct VK video URL when YouTube GitHub-hosted yt-dlp is blocked; validate correct month/title.
- Do not confuse legacy `request.json` with dedicated `probe_request.json`, `parallel_request.json`, `audio_request.json`.
- Use real source frames (full-screen where available, otherwise crop just the slide from video composite); retain all absolute timecodes.
- On audio-only failure, rerun only `parallel-audio.yml`, not successful visual jobs.
- Verify Gmail Sent and attachments before claiming success; do not disable monitoring after temporary errors.
