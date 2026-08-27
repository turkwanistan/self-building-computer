#!/usr/bin/env python3
import json, math, re, sys

def fail(msg):
    raise ValueError(msg)
def finite(v,name):
    try: x=float(v)
    except Exception: fail(f"{name} must be numeric")
    if not math.isfinite(x): fail(f"{name} must be finite")
    return x
def ordered(items,key):
    vals=[finite(x.get(key),key) for x in items]
    return all(a<=b for a,b in zip(vals,vals[1:]))

def profile(t):
    if not isinstance(t,dict) or t.get('schema_version')!='0.1': fail('telemetry schema_version must be 0.1')
    src=t.get('source') or {}; sha=str(src.get('sha256',''))
    if not re.fullmatch(r'[0-9a-f]{64}',sha): fail('source sha256 invalid')
    duration=finite(src.get('duration_seconds'),'duration_seconds')
    if duration<=0: fail('duration_seconds must be positive')
    beats=t.get('beats'); bars=t.get('bars'); sections=t.get('sections')
    if not all(isinstance(x,list) for x in (beats,bars,sections)): fail('beats/bars/sections must be lists')
    if not ordered(beats,'time'): fail('beats are not time ordered')
    if not ordered(bars,'start'): fail('bars are not start ordered')
    if not ordered(sections,'start'): fail('sections are not start ordered')
    bar_ids=set()
    strongest=[]
    for i,b in enumerate(bars):
        idx=int(b.get('index',i)); bar_ids.add(idx)
        start=finite(b.get('start'),'bar.start'); end=finite(b.get('end'),'bar.end')
        if not (0<=start<=end<=duration+1e-6): fail('bar range outside duration')
        e=finite(b.get('average_energy',0.0),'bar.average_energy')
        if not 0<=e<=1: fail('bar average_energy out of range')
        strongest.append({'index':idx,'start':round(start,6),'average_energy':round(e,6)})
    transitions=[]; labels=[]; refs_ok=True
    for i,s in enumerate(sections):
        idx=int(s.get('index',i)); label=str(s.get('label',''))
        if not label: fail('section label missing')
        start=finite(s.get('start'),'section.start'); end=finite(s.get('end'),'section.end')
        if not (0<=start<=end<=duration+1e-6): fail('section range outside duration')
        nov=finite(s.get('novelty',0.0),'section.novelty')
        if not 0<=nov<=1: fail('section novelty out of range')
        refs=s.get('bar_indices',[])
        if not isinstance(refs,list): fail('section bar_indices must be list')
        if any(int(x) not in bar_ids for x in refs): refs_ok=False
        labels.append(label); transitions.append({'section_index':idx,'time':round(start,6),'label':label,'novelty':round(nov,6)})
    if not refs_ok: fail('section references unknown bar')
    strongest=sorted(strongest,key=lambda x:(-x['average_energy'],x['index']))[:3]
    largest=max(transitions,key=lambda x:(x['novelty'],-x['section_index'])) if transitions else None
    warnings=(t.get('diagnostics') or {}).get('warnings',[])
    if not isinstance(warnings,list): fail('diagnostics.warnings must be list')
    bpm=(t.get('global') or {}).get('bpm')
    bpm=None if bpm is None else round(finite(bpm,'bpm'),6)
    return {
      'schema_version':'gen15.telemetry-profile.v1','source_sha256':sha,'duration_seconds':round(duration,6),'bpm':bpm,
      'beat_count':len(beats),'bar_count':len(bars),'section_count':len(sections),'section_pattern':'-'.join(labels),
      'unique_section_labels':len(set(labels)),'repeated_section_instances':len(labels)-len(set(labels)),
      'largest_transition':largest,'strongest_bars':strongest,'warnings':[str(x) for x in warnings],
      'integrity':{'ordered_beats':True,'ordered_bars':True,'ordered_sections':True,'bar_references_valid':True}
    }

try:
    x=json.load(sys.stdin)
    if set(x)!={'telemetry'}: fail('input must contain only telemetry')
    print(json.dumps(profile(x['telemetry']),sort_keys=True,separators=(',',':')))
except Exception as e:
    print(str(e),file=sys.stderr); raise SystemExit(2)
