import os, subprocess, shutil, time, platform, signal

VIDEO_EXTS = {".mod",".mpg",".mpeg",".m2t",".m2ts",".mts",".avi",".mov",".mp4",".m4v",".mkv",".wav",".aif",".aiff"}

def which(tool):
    candidates = [
        "/opt/homebrew/bin/" + tool,
        "/usr/local/bin/" + tool,
        "/usr/bin/" + tool,
        shutil.which(tool) or ""
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None

def probe_duration(ffprobe, path):
    try:
        out = subprocess.check_output([ffprobe, "-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1", path], stderr=subprocess.STDOUT, text=True)
        return max(0.0, float(out.strip()))
    except Exception:
        return 0.0

def is_interlaced(ffprobe, path):
    try:
        out = subprocess.check_output([ffprobe, "-v","error","-select_streams","v:0","-show_entries","stream=field_order,scan_type","-of","default=nw=1:nk=1", path], stderr=subprocess.STDOUT, text=True).lower()
        if "interlaced" in out: return True
        for t in ("tt","bb","tb","bt"):
            if t in out: return True
        return False
    except Exception:
        return False

def build_ffmpeg_args(preset, input_path, out_path, need_deint):
    args = ["-hide_banner","-nostats","-y",
            "-probesize","100M","-analyzeduration","200M",
            "-fflags","+genpts",
            "-progress","pipe:1",
            "-i", input_path,
            "-map","0:v:0","-map","0:a:0?",
            "-c:v", preset["vcodec"],
            "-c:a", preset["acodec"]]
    if preset.get("pixfmt"):
        args += ["-pix_fmt", preset["pixfmt"]]
    args += preset.get("extra", [])
    filters = []
    if need_deint:
        filters.append("bwdif=send_field:parity=auto:deint=all")
    if filters:
        args += ["-vf", ",".join(filters)]
    args += ["-map_metadata","0", out_path]
    return args

def start_ffmpeg(ffmpeg, args):
    return subprocess.Popen([ffmpeg] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)

def parse_progress_line(line):
    if "=" not in line: return None, None
    k, v = line.strip().split("=", 1)
    return k, v

def touch_like(src, dst):
    try:
        st = os.stat(src)
        os.utime(dst, (st.st_atime, st.st_mtime))
    except Exception:
        pass

def copy_metadata_with_exiftool(src, dst):
    exif = which("exiftool")
    if not exif:
        return
    try:
        subprocess.check_call([exif, "-overwrite_original", "-tagsFromFile", src, "-all:all", dst], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def pause_process(proc):
    if platform.system() == "Windows":
        return False
    try:
        os.kill(proc.pid, signal.SIGSTOP); return True
    except Exception:
        return False

def resume_process(proc):
    if platform.system() == "Windows":
        return False
    try:
        os.kill(proc.pid, signal.SIGCONT); return True
    except Exception:
        return False
