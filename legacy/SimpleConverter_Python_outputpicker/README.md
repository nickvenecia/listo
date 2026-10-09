# SimpleConverter (Python, PySide6)

A minimal GUI to batch-convert videos using ffmpeg/ffprobe. Supports H.264 (MP4) and ProRes 422 (MOV), auto-deinterlace, metadata copy, per-file ETA, and batch progress.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
brew install ffmpeg exiftool  # macOS; or your OS package manager
python main.py
```
