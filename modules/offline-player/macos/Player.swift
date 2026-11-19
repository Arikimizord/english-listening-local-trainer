import AppKit
import AVFoundation
import CryptoKit
import UniformTypeIdentifiers
import WebKit

private let audioExtensions = ["mp3", "m4a", "wav", "aac", "mp4"]
private let subtitleExtensions = ["json", "srt"]

private func fileExtension(_ url: URL) -> String {
    url.pathExtension.lowercased()
}

private func stem(_ url: URL) -> String {
    url.deletingPathExtension().lastPathComponent.precomposedStringWithCanonicalMapping.lowercased()
}

private func subtitleOrder(_ urls: [URL]) -> [URL] {
    urls.filter { fileExtension($0) == "json" } + urls.filter { fileExtension($0) == "srt" }
}

private func audioSHA(_ url: URL) throws -> String {
    let file = try FileHandle(forReadingFrom: url)
    defer { try? file.close() }
    var sha = SHA256()
    while let block = try file.read(upToCount: 1024 * 1024), !block.isEmpty {
        sha.update(data: block)
    }
    return sha.finalize().map { String(format: "%02x", $0) }.joined()
}

final class PlayerView: WKWebView {
    var onDrop: (([URL]) -> Void)?

    private func files(_ sender: NSDraggingInfo) -> [URL] {
        let options: [NSPasteboard.ReadingOptionKey: Any] = [.urlReadingFileURLsOnly: true]
        return sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: options) as? [URL] ?? []
    }

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        files(sender).isEmpty ? [] : .copy
    }

    override func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation {
        draggingEntered(sender)
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let urls = files(sender)
        guard !urls.isEmpty else { return false }
        onDrop?(urls)
        return true
    }
}

@MainActor
final class PlayerApp: NSObject, NSApplicationDelegate, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    private let media = AVPlayer()
    private let preferences = "classroomPlayerState"
    private var window: NSWindow!
    private var web: PlayerView!
    private var page: URL!
    private var mediaURL: URL?
    private var mediaKey = ""
    private var id = 0
    private var selection = 0
    private var rate: Float = 1
    private var observation: NSKeyValueObservation?
    private var clock: Any?
    private var notifications: [NSObjectProtocol] = []
    private var mediaReady = false
    private var pageReady = false
    private var incoming: [URL] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let resource = Bundle.main.url(forResource: "听力课堂", withExtension: "html"),
              let resourceDirectory = Bundle.main.resourceURL else {
            let alert = NSAlert()
            alert.messageText = "找不到播放器资源，请重新构建应用。"
            alert.runModal()
            NSApp.terminate(nil)
            return
        }
        page = resource
        let controller = WKUserContentController()
        if let state = UserDefaults.standard.dictionary(forKey: preferences),
           let data = try? JSONSerialization.data(withJSONObject: state),
           let encoded = String(data: data, encoding: .utf8) {
            controller.addUserScript(WKUserScript(source: "window.playerSettings = " + encoded,
                                                  injectionTime: .atDocumentStart, forMainFrameOnly: true))
        }
        controller.add(self, name: "player")
        let configuration = WKWebViewConfiguration()
        configuration.userContentController = controller
        configuration.websiteDataStore = .nonPersistent()
        web = PlayerView(frame: .zero, configuration: configuration)
        web.navigationDelegate = self
        web.registerForDraggedTypes([.fileURL])
        web.onDrop = { [weak self] in self?.open($0) }

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1060, height: 720),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "听力课堂"
        window.contentMinSize = NSSize(width: 760, height: 540)
        window.backgroundColor = NSColor(srgbRed: 252 / 255, green: 246 / 255, blue: 238 / 255, alpha: 1)
        window.collectionBehavior = [.fullScreenPrimary]
        window.delegate = self
        window.contentView = web
        setupMenu()
        web.loadFileURL(resource, allowingReadAccessTo: resourceDirectory)
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func setupMenu() {
        let menu = NSMenu()
        let application = NSMenuItem()
        application.submenu = NSMenu()
        application.submenu?.addItem(withTitle: "退出听力课堂", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(application)
        let file = NSMenuItem()
        file.submenu = NSMenu(title: "文件")
        let openItem = file.submenu?.addItem(withTitle: "打开音频…", action: #selector(openAudio), keyEquivalent: "o")
        openItem?.target = self
        menu.addItem(file)
        let edit = NSMenuItem()
        edit.submenu = NSMenu(title: "编辑")
        edit.submenu?.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.submenu?.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        menu.addItem(edit)
        NSApp.mainMenu = menu
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { remember() }
    func windowWillClose(_ notification: Notification) { remember() }

    func application(_ application: NSApplication, open urls: [URL]) {
        if pageReady { open(urls) } else { incoming.append(contentsOf: urls) }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        pageReady = true
        if !incoming.isEmpty {
            let urls = incoming
            incoming.removeAll()
            open(urls)
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        decisionHandler(navigationAction.request.url == page ? .allow : .cancel)
    }

    private func emit(_ type: String, _ details: [String: Any] = [:]) {
        var event = details
        event["type"] = type
        event["id"] = id
        web.callAsyncJavaScript("window.nativeEvent(event)", arguments: ["event": event],
                                in: nil, in: .page, completionHandler: nil)
    }

    @objc private func openAudio() { choose(audioExtensions + subtitleExtensions, audio: true) }

    private func choose(_ extensions: [String], audio: Bool) {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = extensions.compactMap { UTType(filenameExtension: $0) }
        panel.allowsMultipleSelection = audio
        panel.prompt = "打开"
        panel.beginSheetModal(for: window) { [weak self] result in
            guard result == .OK, let self else { return }
            if audio { self.open(panel.urls) } else { self.loadSubtitles(panel.urls) }
        }
    }

    private func open(_ candidates: [URL]) {
        let urls = candidates.filter(\.isFileURL)
        let explicit = urls.filter { subtitleExtensions.contains(fileExtension($0)) }
        guard let url = urls.first(where: { audioExtensions.contains(fileExtension($0)) }) else {
            if !explicit.isEmpty, mediaURL != nil { loadSubtitles(explicit) }
            else { emit("hint", ["message": "请先打开 MP3、M4A、WAV、AAC 或音频 MP4。"]) }
            return
        }
        remember()
        media.pause()
        if let clock { media.removeTimeObserver(clock); self.clock = nil }
        notifications.forEach { NotificationCenter.default.removeObserver($0) }
        notifications.removeAll()
        observation = nil
        media.replaceCurrentItem(with: nil)
        id += 1
        let openedID = id
        selection += 1
        mediaReady = false
        mediaURL = url
        let attributes = try? url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
        mediaKey = "\(url.path)|\(attributes?.fileSize ?? 0)|\(attributes?.contentModificationDate?.timeIntervalSince1970 ?? 0)"
        emit("opened", ["key": mediaKey, "name": url.lastPathComponent])

        do {
            let file = try FileHandle(forReadingFrom: url)
            defer { try? file.close() }
            let header = try file.read(upToCount: 12) ?? Data()
            var options: [String: Any] = [AVURLAssetPreferPreciseDurationAndTimingKey: true]
            if header.count >= 8, header[4..<8].elementsEqual("ftyp".utf8) {
                options[AVURLAssetOverrideMIMETypeKey] = "audio/mp4"
            }
            let asset = AVURLAsset(url: url, options: options)
            let item = AVPlayerItem(asset: asset, automaticallyLoadedAssetKeys: ["duration"])
            item.audioTimePitchAlgorithm = .timeDomain
            media.replaceCurrentItem(with: item)
            observation = item.observe(\.status, options: [.initial, .new]) { [weak self] _, _ in
                DispatchQueue.main.async { self?.updateStatus(openedID) }
            }
            clock = media.addPeriodicTimeObserver(forInterval: CMTime(value: 60, timescale: 1000), queue: .main) { [weak self] time in
                MainActor.assumeIsolated {
                    guard let self, self.id == openedID, self.media.rate != 0, time.seconds.isFinite else { return }
                    self.emit("time", ["position": time.seconds])
                }
            }
            let center = NotificationCenter.default
            notifications.append(center.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { [weak self] _ in
                DispatchQueue.main.async { if self?.id == openedID { self?.emit("ended") } }
            })
            notifications.append(center.addObserver(forName: .AVPlayerItemFailedToPlayToEndTime, object: item, queue: .main) { [weak self] _ in
                DispatchQueue.main.async { if self?.id == openedID { self?.mediaError() } }
            })
        } catch {
            mediaError()
            return
        }
        let folder = url.deletingLastPathComponent()
        let siblings = (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? []
        let matched = siblings.filter { subtitleExtensions.contains(fileExtension($0)) && stem($0) == stem(url) }
        loadSubtitles(explicit.isEmpty ? matched : explicit)
    }

    private func updateStatus(_ openedID: Int) {
        guard id == openedID, let item = media.currentItem else { return }
        if item.status == .failed { mediaError(); return }
        guard item.status == .readyToPlay, !mediaReady else { return }
        let duration = item.duration.seconds
        guard duration.isFinite, duration > 0 else { mediaError(); return }
        mediaReady = true
        emit("ready", ["duration": duration])
    }

    private func mediaError() {
        media.pause()
        mediaReady = false
        emit("error", ["message": "音频无法播放。" + (media.currentItem?.error?.localizedDescription ?? "请检查文件或编码。")])
    }

    private func loadSubtitles(_ urls: [URL]) {
        guard !urls.isEmpty, let audio = mediaURL else { return }
        selection += 1
        let chosenSelection = selection
        let candidates = subtitleOrder(urls)
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            var digest: Result<String, Error>?
            let files: [[String: String]] = candidates.compactMap { url in
                guard let source = try? String(contentsOf: url, encoding: .utf8) else { return nil }
                var result = ["name": url.lastPathComponent, "text": source]
                if fileExtension(url) == "json",
                   let json = try? JSONSerialization.jsonObject(with: Data(source.utf8)) as? [String: Any],
                   json["audio_sha256"] is String {
                    if digest == nil { digest = Result { try audioSHA(audio) } }
                    if let digest { result["sha"] = try? digest.get() }
                }
                return result
            }
            DispatchQueue.main.async {
                guard let self, self.selection == chosenSelection else { return }
                if files.isEmpty { self.emit("hint", ["message": "字幕无法读取，请检查文件和 UTF-8 编码。"]) }
                else { self.emit("subtitles", ["files": files]) }
            }
        }
    }

    private func remember() {
        let position = media.currentTime().seconds
        guard mediaReady, position.isFinite, !mediaKey.isEmpty else { return }
        var state = UserDefaults.standard.dictionary(forKey: preferences) ?? [:]
        var positions = state["positions"] as? [[Any]] ?? []
        positions.removeAll { ($0.first as? String) == mediaKey }
        positions.append([mediaKey, position])
        state["positions"] = Array(positions.suffix(200))
        UserDefaults.standard.set(state, forKey: preferences)
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, message.frameInfo.request.url == page,
              let fields = message.body as? [String: Any], let action = fields["action"] as? String else { return }
        switch action {
        case "open": openAudio()
        case "subtitle": choose(subtitleExtensions, audio: false)
        case "full": window.toggleFullScreen(nil)
        case "exitFull": if window.styleMask.contains(.fullScreen) { window.toggleFullScreen(nil) }
        case "save":
            if let state = fields["state"] as? [String: Any] { UserDefaults.standard.set(state, forKey: preferences) }
        case "configure":
            if let value = fields["rate"] as? NSNumber {
                rate = value.floatValue
                if media.rate != 0 { media.rate = rate }
            }
            if let value = fields["volume"] as? NSNumber { media.volume = value.floatValue }
        case "play":
            if mediaReady { media.playImmediately(atRate: rate); emit("playing", ["value": true]) }
        case "pause":
            media.pause()
        case "seek":
            guard mediaReady, let position = fields["position"] as? NSNumber,
                  let sequence = fields["sequence"] as? NSNumber else { return }
            let target = CMTime(seconds: position.doubleValue, preferredTimescale: 60000)
            let openedID = id
            media.seek(to: target, toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] succeeded in
                DispatchQueue.main.async {
                    guard let self, self.id == openedID else { return }
                    let time = self.media.currentTime().seconds
                    self.emit("seeked", ["sequence": sequence, "position": time.isFinite ? time : position.doubleValue])
                    if !succeeded, self.media.currentItem?.status == .failed { self.mediaError() }
                }
            }
        default: break
        }
    }
}

@main
struct Launch {
    @MainActor
    static func main() {
        let app = NSApplication.shared
        let delegate = PlayerApp()
        app.setActivationPolicy(.regular)
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
