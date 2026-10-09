import os, sys, time, math
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QThread
from PySide6.QtWidgets import QFileDialog
import psutil

from ffmpeg_utils import which, probe_duration, is_interlaced, build_ffmpeg_args, start_ffmpeg, parse_progress_line, touch_like, copy_metadata_with_exiftool, pause_process, resume_process, VIDEO_EXTS

PRESETS = [
    {"name":"H.264","container":"mp4","vcodec":"libx264","acodec":"aac","pixfmt":"yuv420p","extra":["-preset","veryfast","-crf","18","-b:a","192k","-movflags","+faststart"]},
    {"name":"ProRes 422","container":"mov","vcodec":"prores_ks","acodec":"pcm_s16le","pixfmt":"yuv422p10le","extra":["-profile:v","3"]}
]

def human_eta(seconds: float) -> str:
    if not math.isfinite(seconds) or seconds <= 0: return ""
    s = int(seconds + 0.5); h = s//3600; m = (s%3600)//60; sec = s%60
    return f"{h}h {m}m" if h>0 else (f"{m}m {sec:02d}s" if m>0 else f"{sec}s")

class Job(QtCore.QObject):
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.duration = 0.0
        self.processed = 0.0
        self.progress = 0.0
        self.status = "In queue"
        self.eta_text = ""

class Worker(QThread):
    sig_job_update = Signal(int, float, float, str)
    sig_job_status = Signal(int, str)
    sig_overall = Signal(float, str)
    sig_error = Signal(str)
    sig_done = Signal(bool)

    def __init__(self, jobs, out_dir, preset_index):
        super().__init__()
        self.jobs = jobs; self.out_dir = out_dir; self.preset_index = preset_index
        self._proc = None; self._stop = False; self._paused = False

    def pause(self):
        return pause_process(self._proc) if self._proc else False

    def resume(self):
        return resume_process(self._proc) if self._proc else False

    def stop(self):
        self._stop = True
        try:
            if self._proc: self._proc.terminate()
        except Exception: pass

    def run(self):
        ffmpeg = which("ffmpeg"); ffprobe = which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.sig_error.emit("ffmpeg/ffprobe not found. Install via Homebrew or your package manager.")
            self.sig_done.emit(False); return

        total_dur = 0.0
        for j in self.jobs:
            j.duration = probe_duration(ffprobe, j.path); total_dur += j.duration

        speed_x = 1.0
        for idx, j in enumerate(self.jobs):
            if self._stop: break
            self.sig_job_status.emit(idx, "Queued")
            base = os.path.splitext(os.path.basename(j.path))[0]
            preset = PRESETS[self.preset_index]
            out_dir = self.out_dir if self.out_dir else os.path.dirname(j.path)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{base}.{preset['container']}")

            need_deint = is_interlaced(ffprobe, j.path)
            args = build_ffmpeg_args(preset, j.path, out_path, need_deint)

            try:
                proc = start_ffmpeg(ffmpeg, args); self._proc = proc
                while True:
                    if self._stop: break
                    line = proc.stdout.readline()
                    if not line:
                        if proc.poll() is not None: break
                        time.sleep(0.05); continue
                    k, v = parse_progress_line(line)
                    if k == "out_time_ms":
                        ms = float(v); j.processed = ms / 1_000_000.0
                        j.progress = (j.processed / j.duration) if j.duration>0 else 0.0
                    elif k == "speed":
                        try: speed_x = float(v.replace("x","").strip())
                        except: pass
                    elif k == "progress" and v.strip() == "end":
                        j.processed = j.duration; j.progress = 1.0
                    remain = max(0.0, j.duration - j.processed)
                    j.eta_text = human_eta(remain / max(0.1, speed_x))
                    self.sig_job_update.emit(idx, j.processed, j.progress, j.eta_text)

                rc = proc.wait(); self._proc = None
                if rc == 0:
                    copy_metadata_with_exiftool(j.path, out_path)
                    touch_like(j.path, out_path)
                    self.sig_job_status.emit(idx, "Done ✅")
                else:
                    self.sig_error.emit(proc.stderr.read() or "ffmpeg error")
                    self.sig_job_status.emit(idx, "Failed ❌")

                done = sum(min(x.processed, x.duration) for x in self.jobs)
                overall = done / total_dur if total_dur>0 else 0.0
                remain_all = sum(max(0.0, x.duration - x.processed) for x in self.jobs)
                eta_all = human_eta(remain_all / max(0.1, speed_x))
                self.sig_overall.emit(overall, "Completed" if overall>=0.999 else f"ETA {eta_all}")
            except Exception as e:
                self.sig_error.emit(str(e)); self.sig_job_status.emit(idx, "Failed ❌")
        self.sig_done.emit(True)

class FileList(QtWidgets.QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0,3,parent)
        self.setHorizontalHeaderLabels(["File","Status","ETA"])
        self.horizontalHeader().setStretchLastSection(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setAcceptDrops(True); self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.setShowGrid(False); self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)

    def dragEnterEvent(self, e): 
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls()]
        self.parent().add_paths(urls)

class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SimpleConverter (Python)")
        self.resize(880, 560)
        self.jobs=[]; self.output_dir=None; self.worker=None

        add_btn = QtWidgets.QPushButton("Add Files"); add_btn.clicked.connect(self.on_add_clicked)
        dest_label = QtWidgets.QLabel("Destination:")
        self.dest_btn = QtWidgets.QPushButton("Same as Source"); self.dest_btn.clicked.connect(self.on_pick_output)
        fmt_label = QtWidgets.QLabel("Format:")
        self.fmt_combo = QtWidgets.QComboBox(); [self.fmt_combo.addItem(p["name"]) for p in PRESETS]

        top = QtWidgets.QHBoxLayout()
        top.addWidget(add_btn); top.addSpacing(12)
        top.addWidget(dest_label); top.addWidget(self.dest_btn); top.addSpacing(12)
        top.addWidget(fmt_label); top.addWidget(self.fmt_combo); top.addStretch(1)

        self.table = FileList(self)
        self.placeholder = QtWidgets.QLabel("➕  Drag & drop or click here to add files")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("color: palette(mid); font-size: 18px;")
        self.placeholder.setCursor(Qt.PointingHandCursor)
        self.placeholder.mousePressEvent = lambda e: self.on_add_clicked()
        stackw = QtWidgets.QStackedWidget()
        stackw.addWidget(self.placeholder); stackw.addWidget(self.table)
        self.stackw = stackw; self.stackw.setCurrentIndex(0)

        # If the queue is empty, clicking anywhere in the area opens file picker
        def _stack_mousePressEvent(ev):
            if self.stackw.currentIndex() == 0:
                self.on_add_clicked()
            else:
                QtWidgets.QStackedWidget.mousePressEvent(self.stackw, ev)
        self.stackw.mousePressEvent = _stack_mousePressEvent


        self.start_btn = QtWidgets.QPushButton("Start Conversion"); self.start_btn.clicked.connect(self.on_start)
        self.clear_btn = QtWidgets.QPushButton("Clear"); self.clear_btn.clicked.connect(self.on_clear)
        self.pause_btn = QtWidgets.QPushButton("Pause"); self.pause_btn.setEnabled(False); self.pause_btn.clicked.connect(self.on_pause_resume)
        self.count_label = QtWidgets.QLabel("0/0"); self.eta_all = QtWidgets.QLabel("")
        self.batch_bar = QtWidgets.QProgressBar(); self.batch_bar.setFixedWidth(200)

        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(self.start_btn); bottom.addWidget(self.clear_btn); bottom.addStretch(1)
        bottom.addWidget(self.count_label); bottom.addSpacing(8); bottom.addWidget(self.eta_all); bottom.addSpacing(12)
        bottom.addWidget(self.batch_bar); bottom.addSpacing(8); bottom.addWidget(self.pause_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top); layout.addWidget(self.stackw); layout.addLayout(bottom)

    def add_paths(self, paths):
        files=[]
        for p in paths:
            if os.path.isdir(p):
                for r,_,fs in os.walk(p):
                    for f in fs:
                        if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                            files.append(os.path.join(r,f))
            else:
                if os.path.splitext(p)[1].lower() in VIDEO_EXTS:
                    files.append(p)
        for f in files:
            j = Job(f); self.jobs.append(j)
            row = self.table.rowCount(); self.table.insertRow(row)
            self.table.setItem(row,0,QtWidgets.QTableWidgetItem(os.path.basename(f)))
            self.table.setItem(row,1,QtWidgets.QTableWidgetItem(j.status))
            eta = QtWidgets.QTableWidgetItem(""); eta.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
            self.table.setItem(row,2,eta)
        self.stackw.setCurrentIndex(1 if self.jobs else 0)
        self.count_label.setText(f"0/{len(self.jobs)}")

    def on_add_clicked(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Files", "", "Media Files (*.*)")
        if files:
            self.add_paths(files)
    def on_pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if folder:
            self.output_dir = folder
            self.dest_btn.setText(os.path.basename(folder))
        else:
            self.output_dir = None
            self.dest_btn.setText("Same as Source")


    def on_clear(self):
        self.jobs.clear(); self.table.setRowCount(0); self.stackw.setCurrentIndex(0)
        self.count_label.setText("0/0"); self.batch_bar.setValue(0); self.eta_all.setText(""); self.pause_btn.setEnabled(False)

    def on_start(self):
        if not self.jobs: return
        self.start_btn.setEnabled(False); self.clear_btn.setEnabled(False); self.pause_btn.setEnabled(True)
        self.batch_bar.setValue(0)
        self.worker = Worker(self.jobs, self.output_dir, self.fmt_combo.currentIndex())
        self.worker.sig_job_update.connect(self.on_job_update)
        self.worker.sig_job_status.connect(self.on_job_status)
        self.worker.sig_overall.connect(self.on_overall)
        self.worker.sig_error.connect(self.on_error)
        self.worker.sig_done.connect(self.on_done)
        self.worker.start()

    def on_pause_resume(self):
        if not self.worker: return
        if self.pause_btn.text()=="Pause":
            if self.worker.pause(): self.pause_btn.setText("Resume")
        else:
            if self.worker.resume(): self.pause_btn.setText("Pause")

    @Slot(int, float, float, str)
    def on_job_update(self, idx, processed, progress, eta_text):
        if 0 <= idx < self.table.rowCount():
            self.table.item(idx,2).setText(eta_text)
            self.table.item(idx,1).setText("Queued")
        # show per-file % lightly through overall bar for now
        self.batch_bar.setValue(int(progress*100))

    @Slot(int, str)
    def on_job_status(self, idx, status):
        if 0 <= idx < self.table.rowCount():
            self.table.item(idx,1).setText(status)
        done = sum(1 for j in self.jobs if j.status.startswith("Done"))
        self.count_label.setText(f"{done}/{len(self.jobs)}")

    @Slot(float, str)
    def on_overall(self, prog, eta_txt):
        self.batch_bar.setValue(int(prog*100)); self.eta_all.setText(eta_txt)

    @Slot(str)
    def on_error(self, msg):
        if not msg: return
        m = QtWidgets.QMessageBox(self); m.setWindowTitle("Conversion Error")
        m.setIcon(QtWidgets.QMessageBox.Critical); m.setText("A conversion error occurred."); m.setDetailedText(msg); m.exec()

    @Slot(bool)
    def on_done(self, ok):
        self.start_btn.setEnabled(True); self.clear_btn.setEnabled(True); self.pause_btn.setEnabled(False)
        if all(j.status.startswith("Done") for j in self.jobs if self.jobs):
            QtWidgets.QMessageBox.information(self,"Done","Your files have been converted.")

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow(); w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
