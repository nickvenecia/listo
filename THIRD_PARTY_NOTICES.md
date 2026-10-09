# Third-party software in Listo

The packaged app includes these open-source components. Thank you to their authors.

| Component | License | Source |
|---|---|---|
| FFmpeg (ffmpeg, ffprobe), static builds incl. x264, x265, SVT-AV1, libvpx, LAME, Opus, zimg | GPL-3.0 / GPL-2.0+ | https://ffmpeg.org/download.html · builds: https://ffmpeg.martin-riedl.de, https://github.com/BtbN/FFmpeg-Builds |
| Qt 6 / PySide6 | LGPL-3.0 | https://www.qt.io/download-open-source · https://code.qt.io/cgit/pyside/pyside-setup.git |
| Pillow | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| pillow-heif (libheif, libde265, x265) | BSD-3 / LGPL-3.0 / GPL-2.0+ | https://github.com/bigcat88/pillow_heif |
| rawpy (LibRaw) | MIT / LGPL-2.1 or CDDL-1.0 | https://github.com/letmaik/rawpy |
| NumPy | BSD-3 | https://github.com/numpy/numpy |
| psutil | BSD-3 | https://github.com/giampaolo/psutil |
| Python | PSF License | https://www.python.org |
| Inter typeface | SIL Open Font License 1.1 | https://github.com/rsms/inter (see `listo/assets/fonts/OFL.txt`) |
| VCR OSD Mono typeface, by Riciery Leal (MrManet) | "100% Free" (free for personal and commercial use) | https://www.dafont.com/vcr-osd-mono.font |
| Icons (redrawn line icons) | ISC (Lucide) | https://lucide.dev |

FFmpeg is included as unmodified separate programs that Listo runs. Its full source code is available at the links above.
Qt libraries are shipped as separate shared libraries in the app folder and can be replaced.
