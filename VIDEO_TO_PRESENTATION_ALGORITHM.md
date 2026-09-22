# Video → Presentation + Notes Pipeline

Status: **accepted**
Version: **1.0**
Accepted on: **2026-09-22**
Project: **Презентация по видео**

## Goal

From a long webinar / presentation video, produce two verified deliverables:

1. **PPTX** made from clean screenshots of the original unique slides.
2. **DOCX notes** with a structured transcript/summary tied to slide numbers and absolute timecodes.

The pipeline must avoid low-resolution contact-sheet thumbnails in the final deck and must not invent speaker comments.

## Standard workflow

### Phase A — Probe first 10 minutes

1. Take the first ~10 minutes of the source video.
2. Split the 10-minute probe into **5 parallel jobs of ~2 minutes each** with a small overlap (~3 s).
3. Extract representative frames.
4. Visually inspect the probe and determine a **small fixed area inside the normal slide layout** that stays in the same place throughout the video.
5. Save the crop coordinates.
6. The small crop is used **only for slide-change detection**.

Important:
- Do **not** use a large crop that changes when the presenter enlarges the slide.
- Do **not** use contact-sheet thumbnails as final slide images.
- If the source has no true 480p stream, prefer the next higher source resolution (for example 720p) rather than silently dropping to 360p.

### Phase B — Main visual pass

1. Split the full video into **15 temporal segments** with ~5 s overlap.
2. Run all 15 visual jobs in parallel.
3. For each job:
   - download only its assigned time range;
   - extract frames at ~1 s cadence;
   - compare the fixed small crop to detect changes;
   - save both:
     - the full source frame;
     - the fixed slide crop;
   - also save periodic heartbeat candidates so long static slides are not lost.
4. Aggregate the 15 visual artifacts.

### Phase C — Slide filtering

1. Start from all visual candidates.
2. Detect which candidates actually contain the presentation slide.
3. Separate:
   - **normal-layout slide frames**;
   - **stretched/enlarged slide frames**.
4. **Discard stretched/enlarged frames**.
5. Deduplicate the remaining normal-layout frames.
6. For every unique slide, choose the sharpest/stablest normal-layout frame.
7. Visually inspect the final montage before building the deck.

Accepted AUTOSTAT reference result:
- 589 raw candidates
- 218 frames containing slides
- 210 normal-layout slide frames
- 8 stretched frames discarded
- 20 unique slides retained

### Phase D — PPTX

1. Build the deck only from the selected clean slide screenshots.
2. Preserve the original slide aspect ratio.
3. One screenshot = one PowerPoint slide.
4. Do not reconstruct/edit the slide content unless explicitly requested.
5. Render/inspect the final deck for readability and clipping.

Accepted output example:
- `autostat_august_2026_filtered_screenshots.pptx`

### Phase E — Audio pass

1. Split audio into the same **15 temporal segments** with the same overlap.
2. Run all 15 transcription jobs in parallel.
3. Use Russian transcription for Russian videos.
4. Reference implementation:
   - faster-whisper
   - model: `small`
   - CPU / int8
   - VAD enabled
5. Convert every segment timestamp back to an **absolute video timestamp**.
6. Deduplicate overlap-boundary transcript segments.
7. Merge into one ordered transcript.

### Phase F — Map audio to slides

1. Recover the exact timestamp(s) for each final slide.
2. Build slide display intervals.
3. If the same slide appears more than once, retain all display intervals for that slide.
4. Assign transcript segments to the slide interval(s) by absolute timecode.
5. Create a structured summary that distinguishes:
   - **data visible on the slide**;
   - **what the speakers added verbally**.
6. Never invent commentary or analysis that was not spoken.

Accepted output example:
- `autostat_august_2026_notes_by_slides.docx`

## Required final deliverables

Always produce two separate files:

1. **Presentation**
   - screenshot-based PPTX
   - unique slides only
   - normal-layout frames only

2. **Notes**
   - DOCX (or PDF if explicitly requested)
   - organized by slide
   - slide number
   - timecode / display intervals
   - slide data
   - speaker commentary / summary

## Reliability rules

Use strict state language:
`observed → extracted → transcribed → linked → rendered → checked`

Do not claim:
- that work is running in the background unless an external runner is actually executing;
- that a deck is ready until it exists and has been inspected;
- that comments are from speakers unless they came from the transcript.

Contact sheets are for detection/QA only.

## Failure lessons from the accepted run

- Using contact-sheet thumbnails in the final PPTX produces unreadable slides.
- `height<=480` may select 360p if the platform has no true 480p stream.
- For this AUTOSTAT RUTUBE source, the available streams observed were 360p / 720p / 1080p, so 720p was used for visual extraction.
- Audio jobs must not import Pillow if Pillow is not installed; keep visual-only dependencies lazy or install them explicitly.
- Keep every segment as a separate artifact so a failed branch can be rerun without repeating successful visual work.
- Final human/assistant visual QA is still required after automatic deduplication.

## Repository implementation

Repository: `hcdkutber-boop/Video-Downloader`

Key files:
- `parallel_processor.py`
- `merge_parallel_results.py`
- `merge_audio_results.py`
- `.github/workflows/parallel-probe.yml`
- `.github/workflows/parallel-main.yml`
- `.github/workflows/parallel-audio.yml`
- `probe_request.json`
- `parallel_request.json`
- `audio_request.json`

## New-chat continuation instruction

In a new chat, use:

> Продолжай проект «Презентация по видео» по принятому алгоритму v1.0. Возьми checkpoint с Google Drive / репозитория Video-Downloader и сначала проверь последнюю принятую версию.

