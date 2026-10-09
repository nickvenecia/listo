
import SwiftUI
import AppKit
import Darwin

struct Job: Identifiable, Hashable {
    let id = UUID()
    let inputURL: URL
    var status: String = "In queue"
    var progress: Double = 0.0
    var duration: Double = 0.0
    var processed: Double = 0.0
    var etaText: String = ""
}

struct ConvertPreset: Identifiable, Hashable {
    let id = UUID()
    let name: String           // "H.264", "ProRes 422"
    let containerExt: String   // "mp4" or "mov"
    let vCodec: String
    let aCodec: String
    let pixFmt: String?
    let extraArgs: [String]
}

struct ContentView: View {
    @State private var jobs: [Job] = []
    @State private var outputFolder: URL? = nil
    @State private var isConverting = false
    
    @State private var showMissingToolsAlert = false
    @State private var missingToolsMessage = ""
    
    @State private var showError = false
    @State private var errorMessage = ""
    
    @State private var overallProgress: Double = 0.0
    @State private var overallETA: String = ""
    
    @State private var isPaused: Bool = false
    @State private var currentProcess: Process? = nil
    @State private var currentSpeedX: Double = 1.0
    
    @State private var showBatchUI: Bool = false
    @State private var showDoneAlert: Bool = false
    
    private let presets: [ConvertPreset] = [
        ConvertPreset(
            name: "H.264",
            containerExt: "mp4",
            vCodec: "libx264",
            aCodec: "aac",
            pixFmt: "yuv420p",
            extraArgs: ["-preset","veryfast","-crf","18","-b:a","192k","-movflags","+faststart"]
        ),
        ConvertPreset(
            name: "ProRes 422",
            containerExt: "mov",
            vCodec: "prores_ks",
            aCodec: "pcm_s16le",
            pixFmt: "yuv422p10le",
            extraArgs: ["-profile:v","3"]
        )
    ]
    @State private var selectedPresetIndex: Int = 0
    
    var body: some View {
        VStack(spacing: 16) {
            // Top controls
            HStack(spacing: 12) {
                Button { pickFilesOrFolders() } label: {
                    Label("Add Files", systemImage: "plus.circle").fixedSize(horizontal: true, vertical: false)
                }
                
                // Destination
                HStack(spacing: 8) {
                    Text("Destination:").font(.subheadline).bold()
                    Button { pickOutputFolder() } label: {
                        Label(outputFolder == nil ? "Same as Source" : "Output: \(outputFolder!.lastPathComponent)", systemImage: "folder").fixedSize(horizontal: true, vertical: false)
                    }
                }
                
                // Format
                HStack(spacing: 8) {
                    Text("Format:").font(.subheadline).bold()
                    Picker("", selection: $selectedPresetIndex) {
                        ForEach(presets.indices, id: \.self) { i in
                            Text(presets[i].name).tag(i)
                        }
                    }
                    .labelsHidden()
                    .pickerStyle(.menu)
                    .fixedSize(horizontal: true, vertical: false)
                    .fixedSize(horizontal: true, vertical: false)
                }
                
                Spacer()
            }
            
            // Files list + drag/drop
            ZStack {
                // Background card
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(.quaternary, lineWidth: 1)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                
                // List (back layer)
                List(jobs) { job in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(job.inputURL.lastPathComponent).lineLimit(1)
                            Spacer()
                            Text(job.status + ((job.status.hasPrefix("Queued") || job.status.hasPrefix("Paused")) && !job.etaText.isEmpty ? " · \(job.etaText) left" : ""))
                                .foregroundStyle(.secondary)
                                .monospacedDigit()
                        }
                    }
                    .padding(.vertical, 4)
                }
                .listStyle(.plain)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                
                // Placeholder (front layer)
                if jobs.isEmpty {
                    Button(action: { pickFilesOrFolders() }) {
                        VStack(spacing: 12) {
                            Image(systemName: "plus.app.fill")
                                .font(.system(size: 44, weight: .semibold))
                                .foregroundStyle(.tertiary)
                                .padding(.bottom, 2)
                            Text("Drag & drop or add files to get started")
                                .font(.headline)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .padding(40)
                        .frame(maxWidth: 520)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .frame(minHeight: 260)
            .onDrop(of: [.fileURL], isTargeted: nil) { providers in
                for provider in providers {
                    _ = provider.loadObject(ofClass: URL.self) { url, _ in
                        if let url = url { DispatchQueue.main.async { addURLs([url]) } }
                    }
                }
                return true
            }
            
            // Bottom toolbar with batch progress (opacity-toggled)
            HStack {
                Button {
                    Task { await convertAll() }
                } label: {
                    Label(isConverting ? "Converting…" : "Start Conversion", systemImage: isConverting ? "hourglass" : "arrow.right.circle.fill")
                }
                .keyboardShortcut(.return, modifiers: [])
                .disabled(isConverting || jobs.isEmpty)
                
                Button {
                    jobs.removeAll()
                    overallProgress = 0
                    overallETA = ""
                } label: {
                    Label("Clear", systemImage: "trash")
                }
                .disabled(isConverting || jobs.isEmpty)
                
                Spacer()
                
                HStack(spacing: 12) {
                    HStack(spacing: 8) {
                        let total = jobs.count
                        let done = jobs.filter { $0.status == "Done ✅" }.count
                        Text("\(done)/\(total)").font(.caption).bold().monospacedDigit()
                        Text(overallETA).font(.caption).foregroundStyle(.secondary).monospacedDigit()
                    }
                    ProgressView(value: overallProgress)
                        .progressViewStyle(.linear)
                        .frame(width: 180)
                    
                    if currentProcess != nil {
                        Button(isPaused ? "Resume" : "Pause") {
                            if isPaused { resumeCurrent() } else { pauseCurrent() }
                        }
                        .keyboardShortcut(" ", modifiers: [])
                    } else {
                        Color.clear.frame(width: 0, height: 0)
                    }
                }
                .opacity(showBatchUI ? 1 : 0)
            }
        }
        .padding(20)
         // make app a bit wider so labels/buttons fit
        .onAppear { Task { await checkTools() } }
        .alert("Conversion Error", isPresented: $showError) {
            Button("OK", role: .cancel) {}
        } message: {
            ScrollView { Text(errorMessage).font(.system(.footnote, design: .monospaced)) }
                .frame(maxHeight: 240)
        }
        .alert("Missing Tools", isPresented: $showMissingToolsAlert) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(missingToolsMessage)
        }
        .alert("Done", isPresented: $showDoneAlert) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("Your files have been converted.")
        }
    }
    
    // MARK: - Pickers & adding
    private func pickFilesOrFolders() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.data]
        if panel.runModal() == .OK { addURLs(panel.urls) }
    }
    
    private func addURLs(_ urls: [URL]) {
        for url in urls {
            var isDir: ObjCBool = false
            if FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir), isDir.boolValue {
                if let en = FileManager.default.enumerator(at: url, includingPropertiesForKeys: [.isRegularFileKey], options: [.skipsHiddenFiles]) {
                    for case let f as URL in en {
                        if isRegularFile(f) { jobs.append(Job(inputURL: f)) }
                    }
                }
            } else if isRegularFile(url) {
                jobs.append(Job(inputURL: url))
            }
        }
    }
    
    private func isRegularFile(_ url: URL) -> Bool {
        let exts: Set<String> = ["mod","mpg","mpeg","m2t","m2ts","mts","avi","mov","mp4","m4v","wav","aif","aiff","mkv"]
        let ext = url.pathExtension.lowercased()
        var isDir: ObjCBool = false
        let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir)
        return exists && !isDir.boolValue && (exts.isEmpty || exts.contains(ext))
    }
    
    private func pickOutputFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK { outputFolder = panel.urls.first }
    }
    
    // MARK: - Conversion
    private func convertAll() async {
        guard !isConverting else { return }
        isConverting = true
        isPaused = false
        showBatchUI = true
        defer {
            isConverting = false
            showBatchUI = false
            overallETA = ""
            overallProgress = 0
        }
        
        // Pre-probe durations for ETA/overall progress
        do {
            let ffprobe = try await findTool(named: "ffprobe")
            for i in jobs.indices {
                if jobs[i].duration <= 0 {
                    let d = try? await probeDurationSeconds(ffprobe: ffprobe, input: jobs[i].inputURL)
                    jobs[i].duration = max(0, d ?? 0)
                }
                jobs[i].status = "In queue"
                jobs[i].progress = 0
                jobs[i].processed = 0
                jobs[i].etaText = ""
            }
            overallProgress = 0
            overallETA = ""
        } catch { /* ignore; still run */ }
        
        var anyFailed = false
        
        for i in jobs.indices {
            await MainActor.run { jobs[i].status = "Queued" }
            do {
                try await convertOne(index: i, input: jobs[i].inputURL)
                await MainActor.run {
                    jobs[i].status = "Done ✅"
                    jobs[i].progress = 1.0
                    jobs[i].etaText = ""
                    updateBatchProgress()
                }
            } catch {
                await MainActor.run {
                    jobs[i].status = "Failed ❌"
                    jobs[i].etaText = ""
                    updateBatchProgress()
                    showError = true
                    errorMessage = (error as NSError).userInfo["output"] as? String ?? error.localizedDescription
                    if errorMessage.isEmpty { errorMessage = "Unknown error. Try running from Xcode and check the console output." }
                    let lines = errorMessage.split(whereSeparator: \.isNewline)
                    if lines.count > 80 { errorMessage = lines.suffix(80).joined(separator: "\n") }
                    anyFailed = true
                }
            }
        }
        
        await MainActor.run { if !anyFailed { showDoneAlert = true } }
    }
    
    private func pauseCurrent() {
        guard let p = currentProcess else { return }
        kill(p.processIdentifier, SIGSTOP)
        isPaused = true
        if let j = jobs.firstIndex(where: { $0.status == "Queued" }) {
            jobs[j].status = "Paused ⏸"
        }
    }
    
    private func resumeCurrent() {
        guard let p = currentProcess else { return }
        kill(p.processIdentifier, SIGCONT)
        isPaused = false
        if let j = jobs.firstIndex(where: { $0.status == "Paused ⏸" }) {
            jobs[j].status = "Queued"
        }
    }
    
    private func convertOne(index: Int, input: URL) async throws {
        let ffmpeg = try await findTool(named: "ffmpeg")
        let ffprobe = try await findTool(named: "ffprobe")
        let exif = try? await findTool(named: "exiftool") // optional
        
        let preset = presets[selectedPresetIndex]
        
        let outDir = outputFolder ?? input.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
        let base = input.deletingPathExtension().lastPathComponent
        let out = outDir.appendingPathComponent("\(base).\(preset.containerExt)")
        
        let needsDeinterlace = try await isInterlaced(ffprobe: ffprobe, input: input)
        
        var args: [String] = [
            "-hide_banner", "-nostats",
            "-y",
            "-probesize", "100M",
            "-analyzeduration", "200M",
            "-fflags", "+genpts",
            "-progress", "pipe:1",
            "-i", input.path
        ]
        let isHevcRaw = preset.containerExt.lowercased() == "hevc"
        if isHevcRaw {
            args += ["-map","0:v:0","-c:v", preset.vCodec]
        } else {
            args += ["-map","0:v:0","-map","0:a:0?","-c:v", preset.vCodec,"-c:a", preset.aCodec]
        }
        if let pix = preset.pixFmt { args += ["-pix_fmt", pix] }
        args += preset.extraArgs
        if needsDeinterlace {
            let useBwdif = await hasFFmpegFilter(ffmpeg, name: "bwdif")
            let vf = useBwdif ? "bwdif=send_field:parity=auto:deint=all" : "yadif=mode=send_field:parity=auto:deint=all"
            args += ["-vf", vf]
        }
        args += ["-map_metadata","0"]
        if isHevcRaw { args += ["-f","hevc"] }
        args += [out.path]
        
        let durationSec = jobs[index].duration > 0 ? jobs[index].duration : (try? await probeDurationSeconds(ffprobe: ffprobe, input: input)) ?? 1.0
        
        _ = try await runFFmpegWithProgress(ffmpeg, args: args, duration: durationSec, onLaunch: { proc in
            Task { @MainActor in
                currentProcess = proc
                isPaused = false
            }
        }, onProgress: { processedSec, percent, speedX in
            Task { @MainActor in
                if jobs.indices.contains(index) {
                    jobs[index].processed = processedSec
                    jobs[index].progress = percent
                    currentSpeedX = max(0.1, speedX)
                    if jobs[index].duration > 0 {
                        let remain = max(0, jobs[index].duration - processedSec)
                        jobs[index].etaText = formatETA(seconds: remain / currentSpeedX)
                    }
                    updateBatchProgress()
                }
            }
        })
        
        if let exif = exif {
            _ = try? await run(exif, args: [
                "-overwrite_original", "-tagsFromFile", input.path, "-all:all", out.path
            ])
        }
        
        let touch = "/usr/bin/touch"
        _ = try await run(touch, args: ["-r", input.path, out.path])
        
        let setFileCandidates = ["/usr/bin/SetFile", "/usr/local/bin/SetFile", "/opt/homebrew/bin/SetFile"]
        if let setFile = setFileCandidates.first(where: { FileManager.default.fileExists(atPath: $0) }) {
            let attrs = try FileManager.default.attributesOfItem(atPath: input.path)
            if let mod = attrs[.modificationDate] as? Date {
                let formatter = DateFormatter()
                formatter.dateFormat = "MM/dd/yyyy HH:mm:ss"
                let stamp = formatter.string(from: mod)
                _ = try? await run(setFile, args: ["-d", stamp, out.path])
                _ = try? await run(setFile, args: ["-m", stamp, out.path])
            }
        }
        
        await MainActor.run {
            currentProcess = nil
            isPaused = false
        }
    }
    
    // MARK: - Helpers
    private func hasFFmpegFilter(_ ffmpeg: String, name: String) async -> Bool {
        if let out = try? await run(ffmpeg, args: ["-hide_banner","-v","error","-filters"]) {
            return out.lowercased().contains(name.lowercased())
        }
        return false
    }
    
    private func isInterlaced(ffprobe: String, input: URL) async throws -> Bool {
        let args = [
            "-v","error",
            "-select_streams","v:0",
            "-show_entries","stream=field_order,scan_type",
            "-of","default=nw=1:nk=1",
            input.path
        ]
        let out = try await run(ffprobe, args: args).lowercased()
        if out.contains("interlaced") { return true }
        if out.contains("tt") || out.contains("bb") || out.contains("tb") || out.contains("bt") { return true }
        return false
    }
    
    private func probeDurationSeconds(ffprobe: String, input: URL) async throws -> Double {
        let args = ["-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1", input.path]
        let out = try await run(ffprobe, args: args)
        if let d = Double(out.trimmingCharacters(in: .whitespacesAndNewlines)), d > 0 { return d }
        return 1.0
    }
    
    private func formatETA(seconds: Double) -> String {
        if seconds.isNaN || seconds.isInfinite { return "" }
        let s = Int(seconds.rounded())
        let h = s / 3600
        let m = (s % 3600) / 60
        let sec = s % 60
        if h > 0 { return String(format: "%dh %dm", h, m) }
        if m > 0 { return String(format: "%dm %02ds", m, sec) }
        return String(format: "%ds", sec)
    }
    
    private func updateBatchProgress() {
        let total = jobs.map { $0.duration }.reduce(0, +)
        if total <= 0 { overallProgress = 0; overallETA = ""; return }
        let done = jobs.map { min($0.processed, $0.duration) }.reduce(0, +)
        overallProgress = max(0, min(1, done / total))
        var remaining: Double = 0
        for j in jobs {
            if j.status == "Done ✅" { continue }
            let rem = max(0, j.duration - j.processed)
            remaining += rem / max(0.1, currentSpeedX)
        }
        overallETA = remaining <= 0.5 ? "Completed" : "ETA " + formatETA(seconds: remaining)
    }
    
    private func runFFmpegWithProgress(_ ffmpeg: String, args: [String], duration: Double, onLaunch: @escaping (Process) -> Void, onProgress: @escaping (Double, Double, Double) -> Void) async throws -> String {
        return try await withCheckedThrowingContinuation { cont in
            let task = Process()
            task.executableURL = URL(fileURLWithPath: ffmpeg)
            task.arguments = args
            let outPipe = Pipe()
            let errPipe = Pipe()
            task.standardOutput = outPipe
            task.standardError = errPipe
            
            var lastProcessed: Double = 0.0
            var speedX: Double = 1.0
            
            outPipe.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                guard data.count > 0 else { return }
                if let text = String(data: data, encoding: .utf8) {
                    for raw in text.split(whereSeparator: \.isNewline) {
                        let line = String(raw)
                        if line.hasPrefix("out_time_ms=") {
                            let val = line.replacingOccurrences(of: "out_time_ms=", with: "")
                            if let ms = Double(val) {
                                lastProcessed = (ms / 1_000_000.0)
                                let pct = max(0.0, min(1.0, lastProcessed / max(0.0001, duration)))
                                onProgress(lastProcessed, pct, speedX)
                            }
                        } else if line.hasPrefix("out_time=") && !line.contains("out_time_ms") {
                            let t = line.replacingOccurrences(of: "out_time=", with: "")
                            let parts = t.split(separator: ":")
                            if parts.count >= 3 {
                                let h = Double(parts[0]) ?? 0
                                let m = Double(parts[1]) ?? 0
                                let s = Double(parts[2].split(separator: ".").first ?? "0") ?? 0
                                lastProcessed = h*3600 + m*60 + s
                                let pct = max(0.0, min(1.0, lastProcessed / max(0.0001, duration)))
                                onProgress(lastProcessed, pct, speedX)
                            }
                        } else if line.hasPrefix("speed=") {
                            let v = line.replacingOccurrences(of: "speed=", with: "").replacingOccurrences(of: "x", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
                            if let sp = Double(v), sp.isFinite, sp > 0 {
                                speedX = sp
                                let pct = max(0.0, min(1.0, lastProcessed / max(0.0001, duration)))
                                onProgress(lastProcessed, pct, speedX)
                            }
                        }
                    }
                }
            }
            
            task.terminationHandler = { proc in
                outPipe.fileHandleForReading.readabilityHandler = nil
                let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
                let errOut = String(data: errData, encoding: .utf8) ?? ""
                DispatchQueue.main.async {
                    if currentProcess === task { currentProcess = nil; isPaused = false }
                }
                if proc.terminationStatus == 0 {
                    onProgress(duration, 1.0, speedX)
                    cont.resume(returning: errOut)
                } else {
                    cont.resume(throwing: NSError(domain: "FFmpegError", code: Int(proc.terminationStatus), userInfo: ["output": errOut]))
                }
            }
            
            do { try task.run(); onLaunch(task) } catch { cont.resume(throwing: error) }
        }
    }
    
    private func run(_ launchPath: String, args: [String]) async throws -> String {
        try await withCheckedThrowingContinuation { cont in
            let task = Process()
            task.executableURL = URL(fileURLWithPath: launchPath)
            task.arguments = args
            let pipe = Pipe()
            task.standardError = pipe
            task.standardOutput = pipe
            task.terminationHandler = { proc in
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let output = String(data: data, encoding: .utf8) ?? ""
                if proc.terminationStatus == 0 { cont.resume(returning: output) }
                else { cont.resume(throwing: NSError(domain: "ProcessError", code: Int(proc.terminationStatus), userInfo: ["output": output])) }
            }
            do { try task.run() } catch { cont.resume(throwing: error) }
        }
    }
    
    private func findTool(named name: String) async throws -> String {
        let candidates = ["/opt/homebrew/bin/\(name)", "/usr/local/bin/\(name)", "/usr/bin/\(name)"]
        for c in candidates { if FileManager.default.isExecutableFile(atPath: c) { return c } }
        let whichPath = "/usr/bin/which"
        if let found = try? await run(whichPath, args: [name]), !found.isEmpty {
            return found.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        throw NSError(domain: "ToolNotFound", code: 1, userInfo: [NSLocalizedDescriptionKey: "\(name) not found. Install via Homebrew: brew install \(name)"])
    }
    
    private func checkTools() async {
        var missing: [String] = []
        do { _ = try await findTool(named: "ffmpeg") } catch { missing.append("ffmpeg") }
        do { _ = try await findTool(named: "ffprobe") } catch { missing.append("ffprobe") }
        do { _ = try await findTool(named: "exiftool") } catch { missing.append("exiftool (optional)") }
        if !missing.isEmpty {
            await MainActor.run {
                missingToolsMessage = "You need to install: " + missing.joined(separator: ", ") + ".\n\nInstall with Homebrew:\n  brew install ffmpeg exiftool"
                showMissingToolsAlert = true
            }
        }
    }
}
