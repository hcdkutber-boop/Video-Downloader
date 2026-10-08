# October 2026 AUTOSTAT processing

Source discovered: YouTube recording from 2026-10-06, September 2026 results, approx. 28:55.
Title: `АВТОСТАТ Оперативка. Оперативная информация по авторынку России. Итоги сентября 2026 г.`
URL: https://www.youtube.com/watch?v=ZtAOFHAqOmk
Monthly discovery: complete. Do not search again this month.
Pipeline: v1.0.

Processing status as of 2026-10-08 16:25 MSK:
- Probe config updated and GitHub Actions probe launched.
- First run with `ytsearch1` recovered the YouTube ID `ZtAOFHAqOmk` but failed during download.
- Second run with direct YouTube URL and extra yt-dlp args also failed.
- Blocker: YouTube returns `Sign in to confirm you’re not a bot` on GitHub Actions; no video bytes downloaded.
- Probe outputs, PPTX and DOCX are not created yet.

Next valid continuation:
1) Find a downloadable RuTube/VK mirror, or
2) Obtain/upload an MP4 source file, or
3) Use an authenticated/cookie-based download path outside the public GitHub runner.
