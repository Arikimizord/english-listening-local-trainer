"""Regroup acoustic word timestamps into grammatical sentence candidates, offline.

ASR windows are not sentence boundaries. No timestamps are interpolated and no
saved revision is overwritten. Ambiguous or untimed cuts fail for human review.
"""
import copy
import pathlib
import re

POLICY = 'english-punkt-acoustic-v1'


def regroup(document, tokenizer=None):
    if tokenizer is None:
        import nltk
        nltk.data.path = [str(pathlib.Path(__file__).resolve().parents[1] / 'cache/nltk')]
        tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
    result = copy.deepcopy(document)
    rows = result['segments']
    text = ' '.join(s['text'].strip() for s in rows)
    tokens = list(re.finditer(r'\S+', text))
    words = [copy.deepcopy(w) for s in rows for w in s.get('words', [])]
    if len(tokens) != len(words) or any(t.group() != w['word'] for t, w in zip(tokens, words)):
        raise ValueError('文字与词轴不一致，无法安全重断句；请先对修改过的句子重新对齐。')
    # Punkt knows Dr., Mr., initials and decimal numbers; do not split on every dot.
    spans = list(tokenizer.span_tokenize(text))
    units = []
    for start, end in spans:
        indices = [i for i, t in enumerate(tokens) if t.start() >= start and t.end() <= end]
        if not indices:
            continue
        first, last = indices[0], indices[-1]
        if tokens[first].start() != start or tokens[last].end() != end:
            raise ValueError('断句点落在词内部，需要人工修订。')
        selected = words[first:last+1]
        if selected[0]['start_ms'] is None or selected[-1]['end_ms'] is None:
            raise ValueError('句子首尾词缺少真实时间轴，无法安全设定句末暂停点。')
        a, b = selected[0]['start_ms'], selected[-1]['end_ms']
        if a >= b or (units and a < units[-1]['end_ms']):
            raise ValueError('句子边界发生时间重叠，需要人工核对。')
        sources = [s['id'] for s in rows if s['start_ms'] < b and s['end_ms'] > a]
        units.append({'id': 's%05d' % (len(units)+1), 'start_ms': a, 'end_ms': b,
                      'text': text[start:end], 'words': selected,
                      'source_segment_ids': sources, 'sentence_boundary': 'linguistic_candidate',
                      'review_status': 'pending'})
    if sum(len(s['words']) for s in units) != len(words):
        raise ValueError('断句未覆盖所有词，拒绝生成。')
    for s in units:
        for w in s['words']:
            for key in ('start_ms', 'end_ms'):
                if w[key] is not None and not s['start_ms'] <= w[key] <= s['end_ms']:
                    raise ValueError('词时间越过句界，需重新对齐。')
    result['segments'] = units
    result['sentence_policy'] = POLICY
    result['review_status'] = 'pending'
    result['sentence_report'] = {'before': len(rows), 'after': len(units),
                                 'words_preserved': len(words), 'manual_review_required': True}
    return result
