"""Validate acoustic timestamps and render portable SRT/basic ASS.

No model calls, interpolation or owner approval occur here. ASS uses real word
onsets (not evenly divided text); its centisecond resolution is display-only.
Missing timestamps, text mismatch, overlap, or sub-centisecond onsets fall back
to sentence display with an explicit warning. Full GUI/style acceptance is separate.
"""
from __future__ import annotations
import html
import math
import re
import unicodedata

SCHEMA_VERSION = 1
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def _text(value):
    if not isinstance(value, str):
        raise ValueError('Subtitle text must be a string')
    value = _ANSI.sub('', value).replace('\r\n', '\n').replace('\r', '\n').replace('\t', ' ')
    return ''.join(c for c in value if c == '\n' or unicodedata.category(c) != 'Cc')


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    return float(value)


def _warn(warnings, code, segment_id, **details):
    item = {'code': code, 'segment_id': segment_id, **details}
    if item not in warnings:
        warnings.append(item)


def _bounds(start, end, lo, hi, warnings, sid, label):
    start = _number(start, label + '.start') * 1000
    end = _number(end, label + '.end') * 1000
    if start >= end:
        raise ValueError(f'{label}: start must be before end')
    if start < lo - 50 or end > hi + 50:
        raise ValueError(f'{label}: timestamps outside allowed interval')
    if start < lo or end > hi:
        _warn(warnings, 'boundary_clipped_max_50ms', sid, field=label,
              original_start_ms=start, original_end_ms=end)
    start, end = max(lo, round(start)), min(hi, round(end))
    if start >= end:
        raise ValueError(f'{label}: no positive duration after millisecond conversion')
    return start, end


def normalize_and_validate(payload, duration_seconds):
    """Return integer-ms segments and preserved missing-word timing plus warnings.

    Accepts worker/WhisperX segments with second-valued start/end. Invalid finite
    timings fail; missing word endpoints stay null; existing endpoints are preserved, never fabricated. Source
    segments/words are not mutated. At most 50ms boundary overshoot is clipped
    visibly, including a word's small overshoot of its containing sentence.
    """
    duration = _number(duration_seconds, 'duration_seconds')
    if duration <= 0:
        raise ValueError('duration_seconds must be positive')
    duration_ms = round(duration * 1000)
    if duration_ms < 1:
        raise ValueError('Audio duration is below one millisecond')
    if not isinstance(payload, dict) or not isinstance(payload.get('segments'), list) or not payload['segments']:
        raise ValueError('A nonempty segments list is required')
    warnings, segments = [], []
    previous_start = -1
    for i, source in enumerate(payload['segments']):
        sid = f's{i + 1:05d}'
        if not isinstance(source, dict):
            raise ValueError(f'{sid}: segment must be an object')
        start, end = _bounds(source.get('start'), source.get('end'), 0, duration_ms,
                             warnings, sid, sid)
        if start < previous_start:
            raise ValueError(f'{sid}: segment onsets are not monotonic')
        previous_start = start
        text = _text(source.get('text', '')).strip()
        if not text:
            raise ValueError(f'{sid}: empty subtitle text')
        raw_words = source.get('words', [])
        if raw_words is None:
            raw_words = []
        if not isinstance(raw_words, list):
            raise ValueError(f'{sid}: words must be a list')
        words, previous_word_start = [], -1
        for j, source_word in enumerate(raw_words):
            if not isinstance(source_word, dict):
                raise ValueError(f'{sid}: word must be an object')
            word = _text(source_word.get('word', '')).strip()
            if not word:
                raise ValueError(f'{sid}: empty word text')
            ws, we = source_word.get('start'), source_word.get('end')
            # A provided invalid endpoint is not excused by the other being absent.
            for key, value in [('start', ws), ('end', we)]:
                if value is not None:
                    _number(value, f'{sid}.words[{j}].{key}')
            if ws is None or we is None:
                for value in [ws, we]:
                    if value is not None and not (start - 50 <= value * 1000 <= end + 50):
                        raise ValueError(f'{sid}: provided word endpoint outside segment')
                if any(value is not None and not start <= value * 1000 <= end for value in [ws, we]):
                    _warn(warnings, 'boundary_clipped_max_50ms', sid, field=f'{sid}.words[{j}]', original_start_ms=None if ws is None else ws * 1000, original_end_ms=None if we is None else we * 1000)
                ws = None if ws is None else max(start, min(end, round(ws * 1000)))
                we = None if we is None else max(start, min(end, round(we * 1000)))
                _warn(warnings, 'missing_word_timestamp', sid, word_index=j, word=word)
            else:
                ws, we = _bounds(ws, we, start, end, warnings, sid, f'{sid}.words[{j}]')
                if ws < previous_word_start:
                    raise ValueError(f'{sid}: word onsets are not monotonic')
                previous_word_start = ws
            words.append({'word': word, 'start_ms': ws, 'end_ms': we,
                          'timing_method': 'acoustic', 'timing_complete': ws is not None and we is not None,
                          'review_status': 'pending'})
        if not words:
            _warn(warnings, 'no_word_timestamps', sid)
        segments.append({'id': sid, 'start_ms': start, 'end_ms': end, 'text': text,
                         'words': words, 'review_status': 'pending'})
    result = {'schema_version': SCHEMA_VERSION, 'duration_ms': duration_ms,
              'segments': segments, 'warnings': warnings, 'review_status': 'pending'}
    for segment in segments:
        _karaoke_tokens(segment, warnings)
    return result


def _srt_time(ms):
    hours, tail = divmod(ms, 3600000)
    minutes, tail = divmod(tail, 60000)
    seconds, milli = divmod(tail, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{milli:03}'


def render_srt(normalized):
    """Render sentence SRT, preserving the validated millisecond boundaries."""
    blocks = []
    for i, s in enumerate(normalized['segments'], 1):
        text = html.escape(_text(s['text']), quote=False)
        blocks.append(f"{i}\n{_srt_time(s['start_ms'])} --> {_srt_time(s['end_ms'])}\n{text}")
    return '\n\n'.join(blocks) + '\n'


def _ass_escape(text):
    # Literal fullwidth substitutes prevent ASS override tags and \N injection.
    return _text(text).replace('\\', '\uff3c').replace('{', '\uff5b').replace('}', '\uff5d').replace('\n', r'\N')


def _karaoke_tokens(s, warnings):
    words, sid = s['words'], s['id']
    if not words or any(w['start_ms'] is None or w['end_ms'] is None for w in words):
        _warn(warnings, 'ass_sentence_fallback_missing_times', sid)
        return None
    if ' '.join(s['text'].split()) != ' '.join(w['word'] for w in words):
        _warn(warnings, 'ass_sentence_fallback_text_mismatch', sid)
        return None
    if any(a['end_ms'] > b['start_ms'] for a, b in zip(words, words[1:])):
        _warn(warnings, 'ass_sentence_fallback_overlapping_words', sid)
        return None
    base, finish = s['start_ms'] // 10, (s['end_ms'] + 9) // 10
    starts = [w['start_ms'] // 10 for w in words]
    if any(a >= b for a, b in zip(starts, starts[1:])):
        _warn(warnings, 'ass_sentence_fallback_centisecond_collision', sid)
        return None
    if starts[-1] >= finish:
        _warn(warnings, 'ass_sentence_fallback_centisecond_collision', sid)
        return None
    tokens = []
    if starts[0] > base:
        tokens.append(r'{\k' + str(starts[0] - base) + r'}\h')
    for i, word in enumerate(words):
        next_onset = starts[i + 1] if i + 1 < len(words) else finish
        # Hold through the real inter-word gap; no invented evenly spaced onsets.
        tokens.append(r'{\k' + str(next_onset - starts[i]) + '}' + _ass_escape(word['word'])
                      + (' ' if i + 1 < len(words) else ''))
    return ''.join(tokens)


def _ass_time(cs):
    hours, tail = divmod(cs, 360000)
    minutes, tail = divmod(tail, 6000)
    seconds, centi = divmod(tail, 100)
    return f'{hours}:{minutes:02}:{seconds:02}.{centi:02}'


def render_ass(normalized):
    """Render basic ASS karaoke; fallback reasons append to normalized.warnings.

    ASS onsets are floored and sentence ends ceiled to centiseconds (under 10ms
    display quantization). Word highlighting holds until the next real onset;
    these are display durations, not replacement acoustic end timestamps.
    """
    warnings = normalized.setdefault('warnings', [])
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,42,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines = []
    for s in normalized['segments']:
        text = _karaoke_tokens(s, warnings)
        if text is None:
            text = _ass_escape(s['text'])
        lines.append('Dialogue: 0,' + _ass_time(s['start_ms'] // 10) + ',' +
                     _ass_time((s['end_ms'] + 9) // 10) + ',Default,,0,0,0,,' + text)
    return header + '\n'.join(lines) + '\n'
