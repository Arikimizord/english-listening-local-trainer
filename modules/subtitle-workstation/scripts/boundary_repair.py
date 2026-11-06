"""Conservative offline cross-window echo repair; no lexical deletion list.

Low-confidence whole-word/suffix echoes need TWO contextual decodes agreeing
on the surrounding full words. Genuine repeated speech is retained.
"""
import copy
import re

def key(text):
    return re.sub(r'^\W+|\W+$', '', text.strip()).casefold()

def candidates(rows):
    found=[]
    for i in range(1,len(rows)):
        before=rows[i-1].get('words') or []
        current=rows[i].get('words') or []
        if not before or len(current)<2:continue
        a,b,c=before[-1],current[0],current[1]
        x,y=key(a['word']),key(b['word'])
        if not x or len(y)<3 or not x.endswith(y):continue
        if x!=y and len(x)-len(y)<2:continue
        confidence=b.get('probability')
        if confidence is None or not 0<=confidence<0.15:continue
        if not 0<b['end']-b['start']<=0.35 or not -0.08<=b['start']-a['end']<=0.25:continue
        if not key(c['word']):continue
        found.append({'row':i,'previous':copy.deepcopy(a),'echo':copy.deepcopy(b),'following':copy.deepcopy(c)})
    return found

def adjacency(words,left,right,echo):
    tokens=[key(w['word']) for w in words if key(w['word'])]
    indices=[i for i in range(len(tokens)-1) if tokens[i:i+2]==[left,right]]
    return len(indices)==1 and (indices[0]==0 or tokens[indices[0]-1]!=echo)

def recheck_evidence(evidence):
    result=copy.deepcopy(evidence)
    for item in result:
        a,b,c=(key(item[k]['word']) for k in ('previous','echo','following'))
        for context in item['contexts']:
            words=[{'word':w} for w in context['text'].split()]
            context['supports_removal']=adjacency(words,a,c,b)
            tokens=[key(w['word']) for w in words if key(w['word'])]
            context['supports_original']=sum(tokens[i:i+3]==[a,b,c] for i in range(len(tokens)-2))==1
        item['action']=('remove_confirmed_echo' if all(c['supports_removal'] for c in item['contexts']) else
                        'retain_confirmed_speech' if all(c['supports_original'] for c in item['contexts']) else 'retain_unconfirmed')
        item['decision_policy']='unique-anchor-pair-v2'
    return result

def repair_rows(rows, decode, duration):
    result=copy.deepcopy(rows);evidence=[]
    for item in candidates(rows):
        a,b,c=item['previous'],item['echo'],item['following']
        checks=[]
        for lead,tail in ((7,7),(12,11)):
            start=max(0,a['start']-lead);end=min(duration,c['end']+tail)
            words=decode(start,end)
            checks.append({'start':start,'end':end,'text':' '.join(w['word'].strip() for w in words),
                           'supports_removal':adjacency(words,key(a['word']),key(c['word']),key(b['word']))})
        decision=recheck_evidence([{**item,'contexts':checks}])[0]
        fixed=decision['action']=='remove_confirmed_echo'
        evidence.append(decision)
        if fixed:
            i=item['row'];prior=result[i-1];current=result[i]
            # Include the tail's real ASR interval and a small alignment context;
            # subsequent forced alignment determines the actual acoustic endpoint.
            prior['words'][-1]['end']=max(prior['words'][-1]['end'],b['end'])
            prior['end']=min(c['start'],b['end']+0.25)
            current['words']=current['words'][1:]
            current['text']=' '.join(w['word'].strip() for w in current['words'])
            current['start']=current['words'][0]['start']
    return result,evidence

def apply_to_normalized(document,evidence):
    result=copy.deepcopy(document)
    removed=0
    for item in evidence:
        if item['action']!='remove_confirmed_echo':continue
        pairs=[(s,w) for s in result['segments'] for w in s['words']]
        matches=[i for i,(s,w) in enumerate(pairs) if 0<i<len(pairs)-1
                 and key(w['word'])==key(item['echo']['word'])
                 and key(pairs[i-1][1]['word'])==key(item['previous']['word'])
                 and key(pairs[i+1][1]['word'])==key(item['following']['word'])
                 and w['start_ms'] is not None and abs(w['start_ms']/1000-item['echo']['start'])<0.4]
        if not matches:continue  # Already corrected / absent in a saved revision.
        if len(matches)!=1 or matches[0]==0:raise ValueError('Echo cannot be uniquely mapped to the current transcript')
        i=matches[0];previous,pw=pairs[i-1];current,cw=pairs[i]
        if key(pw['word'])!=key(item['previous']['word']):raise ValueError('Transcript changed near candidate')
        if cw['end_ms'] is None or pw['end_ms'] is None:raise ValueError('Missing acoustic tail endpoints')
        # Preserve the aligned tail interval; never distribute/guess word times.
        pw['end_ms']=max(pw['end_ms'],cw['end_ms']);previous['end_ms']=max(previous['end_ms'],pw['end_ms'])
        current['words'].remove(cw)
        removed+=1
        previous['text']=' '.join(w['word'] for w in previous['words'])
        current['text']=' '.join(w['word'] for w in current['words'])
        if current['words']:
            current['start_ms']=current['words'][0]['start_ms']
        else:result['segments'].remove(current)
    prior=result.get('boundary_repair',{}).get('removed_words',0)
    result['boundary_repair']={'policy':'two-context-local-asr-v1','evidence':evidence,
                               'removed_words':prior+removed}
    return result
