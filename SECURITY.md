# Security

## Reporting a problem

Please report security problems privately, not in a public issue: on GitHub, open this repository's
**Security** tab and choose **Report a vulnerability**. Say what you found and how to see it happen. You'll get
a reply, and a fix in a release, as soon as possible.

## What Listo protects, and how

| What | How |
| --- | --- |
| Your files | Never overwritten: a converted file goes to a hidden temp file first and is moved into place only when it's done; a name that matches the original (case-insensitively too) gets a new one |
| Your settings, recipes, checked captions | Saved only on your computer, in Listo's data folder; atomic writes; anything unreadable is set aside, never overwritten; Back Up… zips them |
| What leaves your computer | Nothing, unless you use it: a pasted video link goes to the link downloader; feedback is kept on your computer until sending is switched on |
| Links | `listo/core/web.py`: only plain http(s) links (no `file://`, `javascript:` or `name@host` tricks) reach the downloader, and always after `--`, so a link can never be read as an option |
| Tools Listo downloads (yt-dlp, Deno) | Only from their official GitHub releases; the published SHA-256 must match |
| Text on screen | File names and anything else from outside are always shown as plain text, never as formatting |
| Running programs | ffmpeg, ffprobe and the downloader get their arguments as a list, never through a shell |
| The single-instance socket | This user's account only; it can only hand files to the open window and bring it forward |
| Updates | Only from this repository's releases; the SHA-256 must match before anything is replaced. What's new is shown as plain words, never as HTML, and only https links in it open |
| The build | GitHub Actions pinned to exact commits; the signing certificate only in the signing step; dependencies pinned, with Dependabot proposing updates |
