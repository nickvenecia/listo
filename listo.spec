# PyInstaller recipe for Listo.   Build with:  pyinstaller listo.spec --noconfirm
# Run `python scripts/fetch_ffmpeg.py` first so ffmpeg gets bundled.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

sys.path.insert(0, str(Path(SPECPATH)))
from listo import __version__  # noqa: E402

ROOT = Path(SPECPATH)
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

datas = [(str(ROOT / "listo" / "assets"), "listo/assets")]
binaries = []
hiddenimports = []

ff = ROOT / "vendor" / "ffmpeg"
if ff.exists():
    for f in ff.iterdir():
        if f.name.startswith("ffmpeg") or f.name.startswith("ffprobe"):
            binaries.append((str(f), "ffmpeg"))
        elif f.suffix == ".txt":
            datas.append((str(f), "ffmpeg"))
else:
    print("WARNING: vendor/ffmpeg missing — the app will look for a system ffmpeg instead.")

try:
    d, b, h = collect_all("pillow_heif")
    datas += d
    binaries += b
    hiddenimports += h
except Exception as e:  # noqa: BLE001
    print(f"WARNING: couldn't collect pillow_heif: {e}")
binaries += collect_dynamic_libs("rawpy")
hiddenimports += ["rawpy._rawpy"]

# Captions: faster-whisper (speech to text) + CTranslate2 (its engine), its voice-detection model,
# and the tokenizer / audio libraries it loads. The speech model itself is downloaded on first use.
# PyAV is left out on purpose (Listo decodes audio with ffmpeg; see captions._without_pyav).
for pkg in ("faster_whisper", "ctranslate2", "tokenizers", "onnxruntime"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: couldn't collect {pkg}: {e}")
hiddenimports += ["huggingface_hub"]

excludes = [
    "av",
    "rawpy.enhance", "scipy", "cv2", "matplotlib", "pandas", "IPython", "imageio", "imageio_ffmpeg",
    "skimage", "PyQt5", "PyQt6", "gi", "numpy.f2py", "numpy.distutils",
    "tkinter", "unittest", "pydoc_data", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtCharts",
    "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDBus", "PySide6.QtOpenGL",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtXml", "PySide6.QtConcurrent",
]

icon_png = ROOT / "listo" / "assets" / "icon.png"
icon = None
if IS_WIN:
    icon = str(ROOT / "build" / "icon.ico")
    Path(icon).parent.mkdir(exist_ok=True)
    from PIL import Image

    Image.open(icon_png).save(icon, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
elif IS_MAC:
    icon = str(icon_png)  # PyInstaller converts PNG -> icns via Pillow

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
# ---- trim things Listo never uses (keeps the download smaller)
def _keep(entry) -> bool:
    d = entry[0].replace("\\", "/").lower()
    if "/qt/translations/" in d or d.endswith(".qm"):
        return False  # Qt's own UI translations (Listo's text is its own)
    if "opengl32sw" in d:
        return False  # Windows software-OpenGL fallback; Listo draws plain widgets
    for plug in ("/plugins/tls/", "/plugins/networkinformation/", "/plugins/qmltooling/", "/plugins/sqldrivers/"):
        if plug in d:
            return False
    return True


a.datas = [x for x in a.datas if _keep(x)]
a.binaries = [x for x in a.binaries if _keep(x)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Listo",
    console=False,
    icon=icon,
    upx=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Listo", upx=False)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="Listo.app",
        icon=icon,
        bundle_identifier="com.badfilmmaker.listo",
        version=__version__,
        info_plist={
            "CFBundleName": "Listo",
            "CFBundleDisplayName": "Listo",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "LSApplicationCategoryType": "public.app-category.video",
            # Lets you drop files on the Dock icon or use "Open With > Listo".
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "Media",
                    "CFBundleTypeRole": "Viewer",
                    "LSHandlerRank": "Alternate",
                    "LSItemContentTypes": [
                        "public.movie", "public.audiovisual-content", "public.audio",
                        "public.image", "public.camera-raw-image", "public.folder",
                    ],
                }
            ],
        },
    )
