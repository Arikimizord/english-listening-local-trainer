"use strict";

const $ = id => document.getElementById(id);
const audio = $("audio");
const harmony = document.documentElement.dataset.platform === "harmonyos";
const bridge = harmony ? undefined : window.webkit?.messageHandlers?.player;
const initialCaption = $("caption").textContent;
const send = (action, fields = {}) => bridge?.postMessage({action, ...fields});
const audioExtensions = new Set(["mp3", "m4a", "wav", "aac", "mp4"]);
const extension = name => name.split(".").pop().toLowerCase();
const baseName = name => name.replace(/\.[^.]+$/, "").normalize("NFC").toLowerCase();
const isSubtitle = name => ["json", "srt"].includes(extension(name));
const limit = (value, low, high, fallback) => Number.isFinite(value) ? Math.min(high, Math.max(low, value)) : fallback;

let settings;
try { settings = window.playerSettings ?? JSON.parse(localStorage.getItem("classroom-player")); } catch {}
const positions = new Map(Array.isArray(settings?.positions) ? settings.positions : []);
let size = limit(settings?.size, 22, 64, 34);
$("volume").value = limit(settings?.volume, 0, 1, 0.8);
$("rate").value = [0.75, 1, 1.25, 1.5].includes(settings?.rate) ? settings.rate : 1;

let id = 0;
let key = "";
let file;
let objectUrl = "";
let audioHash;
let subtitleRequest = 0;
let cues = [];
let pauseSafe = true;
let shown = true;
let active = -2;
let litWord = -1;
let wordNodes = [];
let loop = -1;
let pauseAtEnd = false;
let pausedCue = -1;
let playing = false;
let duration = 0;
let position = 0;
let pendingSeek = null;
let seekSequence = 0;
let scrubbing = false;
let browserTimer;

function rememberPosition() {
  if (key && duration > 0) {
    positions.delete(key);
    positions.set(key, position);
    if (positions.size > 200) positions.delete(positions.keys().next().value);
  }
}

function save() {
  rememberPosition();
  const state = {size, volume: Number($("volume").value), rate: Number($("rate").value), positions: [...positions]};
  if (bridge) send("save", {state});
  else {
    try { localStorage.setItem("classroom-player", JSON.stringify(state)); } catch {}
  }
}

const hint = text => { $("hint").textContent = text; };
const timeLabel = seconds => {
  const total = Math.floor(Math.max(seconds, 0));
  return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
};

function paint(force = false) {
  if (!scrubbing) $("progress").value = position;
  const clock = timeLabel(position) + " / " + timeLabel(duration);
  if ($("clock").textContent !== clock) $("clock").textContent = clock;
  const index = Subtitles.at(cues, position);
  if (force || index !== active) {
    active = index;
    litWord = -1;
    wordNodes = [];
    const caption = $("caption");
    caption.classList.toggle("blind", !shown);
    const cue = cues[active];
    if (!shown) caption.textContent = "字幕已隐藏 · 点击“显示字幕”按钮";
    else if (!cues.length) caption.textContent = key
      ? "此音频尚未加载字幕" : initialCaption;
    else if (!cue?.words.length) caption.textContent = cue?.text ?? "…";
    else {
      const fragment = document.createDocumentFragment();
      for (const word of cue.words) {
        if (wordNodes.length) fragment.append(" ");
        const span = document.createElement("span");
        span.className = "word";
        span.textContent = word.text;
        wordNodes.push(span);
        fragment.append(span);
      }
      caption.replaceChildren(fragment);
    }
  }
  if (wordNodes.length) {
    const current = cues[active].words.findIndex(word => word.start !== null && word.end !== null
      && word.start <= position && position < word.end);
    if (current !== litWord) {
      wordNodes[litWord]?.classList.remove("active");
      wordNodes[current]?.classList.add("active");
      litWord = current;
    }
  }
}

function flags() {
  $("loop").textContent = "单句循环：" + (loop >= 0 ? "开" : "关");
  $("loop").setAttribute("aria-pressed", String(loop >= 0));
  $("autoPause").textContent = "句末暂停：" + (pauseAtEnd ? "开" : "关");
  $("autoPause").setAttribute("aria-pressed", String(pauseAtEnd));
}

function setPlaying(value) {
  playing = value;
  $("play").textContent = playing ? "暂停" : "播放";
  if (!bridge) {
    clearInterval(browserTimer);
    if (value) browserTimer = setInterval(() => receiveTime(audio.currentTime), 60);
  }
}

function rateAndVolume() {
  const rate = Number($("rate").value);
  const volume = Number($("volume").value);
  if (bridge) send("configure", {rate, volume});
  else { audio.playbackRate = rate; audio.volume = volume; }
}

function play() {
  if (!duration) { if (!key) $("open").click(); return; }
  if (playing) { pause(); return; }
  if (pausedCue >= 0 && cues[pausedCue + 1]) seek(cues[pausedCue + 1].start);
  pausedCue = -1;
  start();
}

function start() {
  if (bridge) send("play");
  else audio.play().catch(error => { if (error.name !== "AbortError") hint("无法开始播放，请重试或检查音频格式。"); });
}

function pause() {
  setPlaying(false);
  if (bridge) send("pause");
  else audio.pause();
  save();
}

function currentOrNext() {
  const current = Subtitles.at(cues, position);
  return current >= 0 ? current : Math.min(Subtitles.lowerBound(cues, position, "start"), cues.length - 1);
}

function seek(target, preserveMode = false) {
  if (!duration) return;
  position = limit(target, 0, duration, 0);
  if (!preserveMode) {
    pausedCue = -1;
    if (loop >= 0) loop = currentOrNext();
  }
  if (bridge) {
    pendingSeek = ++seekSequence;
    send("seek", {position, sequence: pendingSeek});
  } else {
    audio.currentTime = position;
  }
  paint();
}

function receiveTime(time) {
  if (!duration || !Number.isFinite(time) || pendingSeek !== null || (!bridge && audio.seeking)) return;
  if (playing && loop >= 0 && time >= cues[loop].end) {
    seek(cues[loop].start, true);
    return;
  }
  if (playing && pauseAtEnd) {
    const ended = Subtitles.lowerBound(cues, position, "end", false);
    const cue = cues[ended];
    if (cue && time >= cue.end) {
      pause();
      pausedCue = ended;
      seek(Math.max(cue.start, cue.end - 0.02), true);
      return;
    }
  }
  position = time;
  paint();
}

function finished() {
  if (pausedCue >= 0 && !playing) return;
  receiveTime(duration);
  if (pausedCue >= 0) return;
  if (loop >= 0 && cues[loop].start < duration) {
    seek(cues[loop].start, true);
    start();
  } else {
    setPlaying(false);
    seek(0);
    save();
  }
}

function move(direction) {
  if (!duration || !cues.length) { hint("切句需要先加载 JSON 或 SRT 字幕。"); return; }
  const current = Subtitles.at(cues, position);
  const next = Subtitles.lowerBound(cues, position, "start", false);
  const index = Math.min(cues.length - 1, Math.max(0, current >= 0 ? current + direction : next - (direction < 0 ? 1 : 0)));
  seek(cues[index].start, true);
  pausedCue = -1;
  if (loop >= 0) loop = index;
  start();
}

function opened(mediaName, mediaKey, mediaId = id + 1) {
  id = mediaId;
  key = mediaKey;
  subtitleRequest = 0;
  duration = position = 0;
  pendingSeek = null;
  cues = [];
  pauseSafe = true;
  loop = pausedCue = -1;
  pauseAtEnd = false;
  setPlaying(false);
  $("filename").textContent = $("filename").title = mediaName;
  $("progress").max = 1;
  $("progress").disabled = true;
  hint("音频可直接播放。可同时打开同名字幕，或点击“选择字幕”。");
  flags();
  paint(true);
}

function ready(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    hint("无法读取音频时长，请检查文件。");
    return;
  }
  duration = seconds;
  $("progress").max = seconds;
  $("progress").disabled = false;
  const remembered = positions.get(key);
  if (Number.isFinite(remembered) && remembered > 0 && remembered < seconds - 2) seek(remembered);
  rateAndVolume();
  paint();
}

async function importSubtitles(candidates, mediaId = id, request = ++subtitleRequest) {
  let error;
  for (const candidate of candidates) {
    try {
      const source = typeof candidate.text === "string" ? candidate.text : await candidate.text();
      const data = extension(candidate.name) === "json"
        ? await Subtitles.parseJson(source, async () => {
          if (bridge) {
            if (!candidate.sha) throw Error(candidate.hashError || "无法验证音频哈希。");
            return candidate.sha;
          }
          if (harmony) {
            audioHash ??= hashHarmonyAudio(file);
            return audioHash;
          }
          if (!crypto.subtle) throw Error("当前浏览器无法验证音频哈希，请用 Mac App 或 SRT。");
          const selectedFile = file;
          audioHash ??= selectedFile.arrayBuffer().then(bytes => crypto.subtle.digest("SHA-256", bytes))
            .then(bytes => Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, "0")).join(""));
          return audioHash;
        })
        : Subtitles.parseSrt(source);
      if (mediaId !== id || request !== subtitleRequest) return;
      cues = data.cues;
      pauseSafe = data.pauseSafe;
      loop = pausedCue = -1;
      pauseAtEnd = false;
      flags();
      paint(true);
      const type = cues.some(cue => cue.words.length) ? "真实词轴高亮" : "普通字幕";
      hint(`已加载 ${cues.length} 句 · ${type}${error ? " · JSON 未通过校验，已使用备用 SRT" : ""}`);
      return;
    } catch (failure) { error = failure; }
  }
  if (error && mediaId === id && request === subtitleRequest) hint("字幕未加载：" + error.message);
}

function preferred(files) {
  return [...files].filter(item => isSubtitle(item.name)).sort((a, b) => Number(extension(a.name) === "srt") - Number(extension(b.name) === "srt"));
}

async function openFiles(items) {
  const files = [...items];
  const next = files.find(candidate => audioExtensions.has(extension(candidate.name)));
  if (!next) {
    if (key && preferred(files).length) void importSubtitles(preferred(files));
    else if (files.length) hint("请先打开 MP3、M4A、WAV、AAC 或音频 MP4。");
    return;
  }
  save();
  audio.pause();
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  file = next;
  audioHash = undefined;
  opened(next.name, [next.name, next.size, next.lastModified].join("|"));
  const currentId = id;
  const choices = preferred(files);
  const sameDirectory = candidate => (candidate.webkitRelativePath || candidate.name).split("/").slice(0, -1).join("/")
    === (next.webkitRelativePath || next.name).split("/").slice(0, -1).join("/");
  const matched = choices.filter(candidate => baseName(candidate.name) === baseName(next.name) && sameDirectory(candidate));
  if (matched.length) void importSubtitles(matched);
  else if (!next.webkitRelativePath && choices.length) void importSubtitles(choices);
  try {
    const head = new Uint8Array(await next.slice(0, 12).arrayBuffer());
    if (currentId !== id) return;
    const mime = String.fromCharCode(...head.slice(4, 8)) === "ftyp" ? "audio/mp4"
      : ({mp3: "audio/mpeg", m4a: "audio/mp4", mp4: "audio/mp4", wav: "audio/wav", aac: "audio/aac"})[extension(next.name)];
    objectUrl = URL.createObjectURL(next.slice(0, next.size, mime));
    audio.src = objectUrl;
  } catch {
    if (currentId === id) hint("无法读取所选音频。");
  }
}

window.nativeEvent = event => {
  if (event.type === "opened") {
    rememberPosition();
    opened(event.name, event.key, event.id);
    return;
  }
  if (event.type === "save") { save(); return; }
  if (event.type === "hint") { hint(event.message); return; }
  if (event.id !== id) return;
  switch (event.type) {
    case "ready": ready(event.duration); break;
    case "time": if (playing) receiveTime(event.position); break;
    case "playing": setPlaying(event.value); break;
    case "ended": if (pendingSeek === null) finished(); break;
    case "seeked":
      if (event.sequence === pendingSeek) { pendingSeek = null; position = event.position; paint(); }
      break;
    case "subtitles": void importSubtitles(event.files, event.id, ++subtitleRequest); break;
    case "error": setPlaying(false); hint(event.message); break;
  }
};

audio.addEventListener("loadedmetadata", () => ready(audio.duration));
audio.addEventListener("play", () => setPlaying(true));
audio.addEventListener("pause", () => { if (!audio.ended) setPlaying(false); });
audio.addEventListener("ended", finished);
audio.addEventListener("error", () => {
  setPlaying(false);
  hint(harmony ? "当前浏览器无法解码此音频，请使用标准 MP3 或 WAV。" : "音频无法解码，请检查文件或使用 Mac App。");
});

function applyFont() { document.documentElement.style.setProperty("--caption-size", size + "px"); }
applyFont();
$("play").onclick = play;
$("prev").onclick = () => move(-1);
$("next").onclick = () => move(1);
$("back").onclick = () => seek(position - 15);
$("forward").onclick = () => seek(position + 15);
$("open").onclick = () => bridge ? send("open") : $("mediaInput").click();
$("folder").hidden = !!bridge || harmony;
$("folder").onclick = () => $("folderInput").click();
$("subtitle").onclick = () => {
  if (!key) { hint("请先打开音频，再选择对应字幕。"); return; }
  if (bridge) send("subtitle");
  else $("subtitleInput").click();
};
for (const input of [$("mediaInput"), $("subtitleInput"), $("folderInput")]) {
  input.onchange = () => { void openFiles(input.files); input.value = ""; };
}
$("loop").onclick = () => {
  if (!cues.length) { hint("单句循环需要先加载字幕。"); return; }
  loop = loop >= 0 ? -1 : currentOrNext();
  if (loop >= 0) { pauseAtEnd = false; pausedCue = -1; }
  flags();
};
$("autoPause").onclick = () => {
  if (!cues.length) { hint("句末暂停需要先加载字幕。"); return; }
  if (!pauseSafe) { hint("此字幕断句尚未完成，请先在工作台修订。"); return; }
  pauseAtEnd = !pauseAtEnd;
  pausedCue = -1;
  loop = -1;
  flags();
};
$("visibility").onclick = () => {
  shown = !shown;
  $("visibility").textContent = shown ? "隐藏字幕" : "显示字幕";
  $("visibility").setAttribute("aria-pressed", String(!shown));
  paint(true);
};
for (const [button, delta] of [["smaller", -4], ["larger", 4]]) {
  $(button).onclick = () => { size = limit(size + delta, 22, 64, 34); applyFont(); save(); };
}
$("rate").onchange = $("volume").oninput = () => { rateAndVolume(); save(); };
const progress = $("progress");
progress.addEventListener("pointerdown", () => { scrubbing = true; });
window.addEventListener("pointerup", () => {
  if (scrubbing) { scrubbing = false; seek(Number(progress.value)); }
});
window.addEventListener("pointercancel", () => { scrubbing = false; paint(); });
progress.onchange = () => { if (!scrubbing) seek(Number(progress.value)); };

function full() {
  if (bridge) { send("full"); return; }
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    (document.exitFullscreen ?? document.webkitExitFullscreen).call(document);
  } else {
    const enter = document.documentElement.requestFullscreen ?? document.documentElement.webkitRequestFullscreen;
    if (enter) enter.call(document.documentElement)?.catch?.(() => hint("请用浏览器的全屏菜单。"));
    else hint("请用浏览器的全屏菜单。");
  }
}
$("fullscreen").onclick = full;
$("player").addEventListener("click", event => {
  if (event.detail > 0 && event.target instanceof HTMLButtonElement) event.target.blur();
});
window.addEventListener("keydown", event => {
  if (!$("splash").hidden || event.isComposing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target.matches("input, select") || (event.target.matches("button") && event.key === " ")) return;
  const button = {" ": "play", arrowleft: "prev", arrowright: "next", h: "visibility", f11: "fullscreen"}[event.key.toLowerCase()];
  if (button) { event.preventDefault(); $(button).click(); }
  if (event.key === "Escape" && bridge) send("exitFull");
});
if (!bridge) {
  window.addEventListener("dragover", event => {
    if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); $("player").classList.add("dragging"); }
  });
  window.addEventListener("dragleave", event => { if (!event.relatedTarget) $("player").classList.remove("dragging"); });
  window.addEventListener("drop", event => {
    event.preventDefault();
    $("player").classList.remove("dragging");
    void openFiles(event.dataTransfer.files);
  });
  window.addEventListener("pagehide", save);
  document.addEventListener("visibilitychange", () => { if (document.hidden) save(); });
}

const splashStart = performance.now();
const animation = setInterval(() => {
  const elapsed = performance.now() - splashStart;
  $("percent").textContent = Math.min(100, Math.floor(elapsed / 26.4)) + "%";
  if (elapsed >= 3000) {
    clearInterval(animation);
    $("splash").hidden = true;
    $("player").inert = false;
  }
}, 50);
