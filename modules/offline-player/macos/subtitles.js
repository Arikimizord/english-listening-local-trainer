"use strict";

const Subtitles = (() => {
  function parseSrt(source) {
    const timing = /^(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})[ \t]*-->[ \t]*(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})[^\n]*\n([\s\S]+)$/m;
    const seconds = (match, i) => Number(match[i]) * 3600 + Number(match[i + 1]) * 60
      + Number(match[i + 2]) + Number(match[i + 3]) / 1000;
    const cues = [];
    for (const block of source.replace(/\r\n?/g, "\n").trim().split(/\n[ \t]*\n/)) {
      const match = timing.exec(block);
      if (!match) continue;
      const start = seconds(match, 1);
      const end = seconds(match, 5);
      const text = match[9].replace(/<\/?(?:b|i|u|font)(?:\s[^>]*)?>/gi, "").trim();
      if (end > start && text) cues.push({start, end, text, words: []});
    }
    cues.sort((a, b) => a.start - b.start);
    validate(cues);
    return {cues, pauseSafe: true};
  }

  async function parseJson(source, hashAudio) {
    const document = JSON.parse(source.replace(/^\uFEFF/, ""));
    if (!Array.isArray(document?.segments)) throw Error("JSON 缺少 segments 字幕列表。");
    if (document.audio_sha256 != null) {
      if (!/^[0-9a-f]{64}$/i.test(document.audio_sha256)
          || String(await hashAudio()).toLowerCase() !== document.audio_sha256.toLowerCase()) {
        throw Error("字幕与音频哈希不符。");
      }
    }
    const time = value => {
      if (typeof value !== "number" || !Number.isFinite(value) || value < 0) throw Error("字幕时间非法。");
      return value / 1000;
    };
    const cues = document.segments.map(row => {
      const start = time(row.start_ms);
      const end = time(row.end_ms);
      const text = typeof row.text === "string" ? row.text.trim() : "";
      let previousEnd = start;
      let words = (row.words ?? []).map(word => {
        const a = word.start_ms == null ? null : time(word.start_ms);
        const b = word.end_ms == null ? null : time(word.end_ms);
        if ((a !== null && (a < previousEnd || a > end))
            || (b !== null && (b < start || b > end))
            || (a !== null && b !== null && a >= b)) throw Error("词时间越过句界或重叠。");
        if (b !== null) previousEnd = Math.max(previousEnd, b);
        return {start: a, end: b, text: word.word};
      });
      if (words.some(word => typeof word.text !== "string") ||
          words.map(word => word.text).join(" ") !== text.replace(/\s+/g, " ")) words = [];
      return {start, end, text, words};
    });
    validate(cues);
    return {cues, pauseSafe: document.sentence_policy !== "unresolved"};
  }

  function validate(cues) {
    if (!cues.length) throw Error("没有读到有效字幕，请检查 UTF-8 文件。");
    for (let i = 0; i < cues.length; i += 1) {
      const cue = cues[i];
      if (cue.end <= cue.start || !cue.text || (i > 0 && cue.start < cues[i - 1].end)) {
        throw Error("字幕时间非法或重叠，请先在字幕工作台修订。");
      }
    }
  }

  function lowerBound(cues, time, field, inclusive = true) {
    let low = 0;
    let high = cues.length;
    while (low < high) {
      const mid = (low + high) >>> 1;
      if (cues[mid][field] < time || (!inclusive && cues[mid][field] === time)) low = mid + 1;
      else high = mid;
    }
    return low;
  }

  function at(cues, time) {
    const index = lowerBound(cues, time, "start", false) - 1;
    return index >= 0 && time < cues[index].end ? index : -1;
  }

  return {parseSrt, parseJson, lowerBound, at};
})();
