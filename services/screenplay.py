"""Mixed-format screenplay parsing with immutable character-offset source spans."""
import re
from .schema import UserError

UNKNOWN='Confirmation Required'
TYPES=['Scene Heading','Sequence Heading','Time Change','Dialogue','Action','Reaction','Parenthetical',
       'Transition','On-Screen Text','Title Card','Stage Card','Montage','Voice Over','SFX','Music Cue',
       'Camera Direction','POV','Split Screen','Split Screen Panel','Speed Treatment','Reveal','Insert','VFX','Production Note','Unknown']
SCENE=re.compile(r'^(?:\d+[.)]?\s+)?(INT\.?\s*/\s*EXT\.?|INT\.?|EXT\.?|I/E\.?)\s*(?:[.\-]\s*|\s+)(.+)',re.I)
LABEL=re.compile(r"^([\w][\w '\-]{0,40}?)(?:\s*\((V\.?O\.?|O\.?S\.?|O\.?C\.?)\))?\s*:\s*(.*)$",re.I)
TIME=re.compile(r'^(?:FLASHBACK\b|BEGIN FLASHBACK\b|\d+\s+(?:seconds?|minutes?|hours?|days?|weeks?|years?)\s+(?:earlier|later)\b|LATER(?: THAT (?:DAY|NIGHT))?\s*[:.\-]?$|THE NEXT (?:MORNING|DAY|NIGHT)\b|YEARS? (?:EARLIER|LATER)\b)',re.I)
RETURN=re.compile(r'^(?:BACK TO (?:THE )?PRESENT|RETURN TO (?:THE )?PRESENT|PRESENT DAY|END FLASHBACK|BACK TO SCENE)\b',re.I)
SEQUENCE=re.compile(r'^(?:BEGIN\s+)?(MONTAGE|COMPILATION)\b\s*:?\s*(.*)',re.I)
END_SEQUENCE=re.compile(r'^END\s+(MONTAGE|COMPILATION)\b',re.I)
PREFIXES=[
    (r'^(?:SHOTS?\s+\d+|PROCESS\s*:|B[- ]ROLL\b|COVERAGE\s*:|MULTIPLE\s+.*SHOTS|VARIOUS\s+.*SHOTS)','Coverage'),
    (r'^(?:LIGHTING|WARDROBE|COSTUME|HAIR|MAKEUP|ART|EXTRAS|BACKGROUND|PROPS)\s*:','Production Note'),
    (r'^(?:TITLE CARD|TITLE)\s*:', 'Title Card'),(r'^STAGE\s+\d+\s*:', 'Stage Card'),
    (r'^(?:ON[- ]SCREEN TEXT|SUPER|TEXT ON SCREEN|GRAPHIC|GRAPHICS)\s*:', 'On-Screen Text'),
    (r'^(?:SFX|SOUND EFFECT|PRACTICAL EFFECT)\s*:', 'SFX'),(r'^(?:MUSIC|SONG|SCORE)\s*:', 'Music Cue'),
    (r'^(?:VO|V\.?O\.?|VOICE[- ]OVER)\s*:', 'Voice Over'),(r'^(?:VFX|POST)\s*:', 'VFX'),
    (r'^(?:CUT TO|FADE IN|FADE OUT|DISSOLVE TO|SMASH CUT|MATCH CUT)\b', 'Transition'),
    (r'^(?:PHONE POV|POV|POINT OF VIEW)\b', 'POV'),(r'^SPLIT[- ]SCREEN\b','Split Screen'),
    (r'^(?:LEFT|RIGHT)(?: PANEL| SIDE)?\s*:','Split Screen Panel'),
    (r'^(?:SLOW[- ]MOTION|SLOW[- ]MO|NORMAL SPEED|REAL TIME|SPEED RAMP)\b','Speed Treatment'),
    (r'^(?:INSERT|DETAIL SHOT)\b','Insert'),(r'^(?:REVEAL|WE REVEAL)\b','Reveal'),
    (r'^(?:REACTION|REACTION SHOT)\b','Reaction'),
    (r'^(?:ECU|MCU|CU|MS|WS|LONG TAKE|CAMERA|CLOSE[- ]UP|EXTREME CLOSE[- ]UP|WIDE(?: SHOT)?|MASTER SHOT|TWO SHOT|OTS|OVER[- ]THE[- ]SHOULDER|PAN|TILT|TRACK|DOLLY|HIGH ANGLE|LOW ANGLE|TOP SHOT)\b','Camera Direction'),
]
ACTION_VERBS=r'(?:slams?|opens?|closes?|enters?|exits?|picks?|puts?|turns?|walks?|runs?|looks?|stares?|freezes?|flinches?|recoils?|reveals?|tears?|rips?|drops?|grabs?|holds?|sits?|stands?|smiles?|nods?|raises?|crosses?|takes?|hands?|pushes?|pulls?|wears?|is wearing|explodes?|bursts?)'
ACTION=re.compile(r'^(?:[\w’\-]+(?:\s+[\w’\-]+){0,4})\s+'+ACTION_VERBS+r'\b',re.I)

def clean_line(line):
    value=re.sub(r'[\t ]+',' ',line).strip().lstrip('\ufeff')
    if value.startswith(('"','“')):value=value[1:]
    if value.endswith('"') and value.count('"')%2:value=value[:-1]
    if value.endswith('”') and value.count('”')>value.count('“'):value=value[:-1]
    return value.strip()

def source_block(raw,elements):
    if not elements:return '',[]
    start=min(e['source_start'] for e in elements);end=max(e['source_end'] for e in elements)
    return raw[start:end],[{'start':start,'end':end}]

def analyze(raw):
    if not isinstance(raw,str) or not raw.strip():raise UserError('Paste a screenplay first, or upload an Excel shot sheet.')
    if len(raw)>100000:raise UserError('This script exceeds 100,000 characters. Split it into smaller sequences.')
    lines=[];offset=0
    for original in raw.splitlines(keepends=True):
        content=original.rstrip('\r\n');lines.append((clean_line(content),offset,offset+len(content)));offset+=len(original)
    scene_list=[];elements=[];speaker='';voice=False;speaker_start=None;has_spoken=False
    context={'location':UNKNOWN,'day_night':UNKNOWN,'interior_exterior':UNKNOWN,'temporal_context':'Present',
             'sequence_type':'Scene','cast_present':[],'costumes':{},'props':[],'lighting':[],
             'art_setup':[],'extras':[],'context_facts':{},'context_assumptions':[]}
    saved_present=None;sequence_return=None
    def new_scene(name,reason):
        nonlocal current
        current={'number':str(len(scene_list)+1),'heading':name,'name':name,'boundary_reason':reason,
                 **context,'context':{**context,'cast_present':list(context['cast_present'])},'elements':[]}
    current={};new_scene('Unspecified scene','Start of script; location unspecified')
    def push_scene():
        if any(e['type'] not in ('Scene Heading','Sequence Heading','Time Change','Parenthetical','Transition') for e in current['elements']):scene_list.append(current)
    def change(name,reason,updates):
        nonlocal context,speaker,speaker_start,has_spoken
        old=current['elements'];before=len(scene_list);push_scene();carry=old if len(scene_list)==before else []
        context={**context,**updates};speaker='';speaker_start=None;has_spoken=False
        new_scene(name,reason)
        current['elements'].extend(carry)
    def emit(kind,value,start,end,who='',heard=False):
        if kind in ('Dialogue','Voice Over','Action') and end-start>1800:
            # Preserve exact offsets. Long passages continue at complete sentences where possible.
            cursor=start
            while cursor<end:
                cap=min(cursor+1800,end)
                if cap<end:
                    breaks=list(re.finditer(r'(?<=[.!?])\s+',raw[cursor:cap]))
                    if breaks:cap=cursor+breaks[-1].end()
                    else:
                        space=raw.rfind(' ',cursor+900,cap)
                        if space>cursor:cap=space+1
                part=clean_line(raw[cursor:cap]);label_part=LABEL.match(part)
                if label_part and label_part[1].strip()==who:part=label_part[3]
                emit(kind,part,cursor,cap,who,heard);cursor=cap
            return
        e={'id':len(elements)+1,'type':kind,'text':value,'speaker':who,'heard_only':heard,
           'scene':current['number'],'source_start':start,'source_end':end,'raw':raw[start:end]}
        elements.append(e);current['elements'].append(e)
        return e
    for i,(line,start,end) in enumerate(lines):
        if not line or not re.search(r'\w',line):
            if has_spoken:speaker='';speaker_start=None;has_spoken=False
            continue
        heading=SCENE.match(line)
        if heading:
            parts=re.split(r'\s+[-–—]\s+',heading[2]);location=parts[0].strip();day=parts[-1].strip() if len(parts)>1 else context['day_night']
            ie=heading[1].replace('.','').replace(' ','').upper()
            updates={'location':location,'day_night':day,'interior_exterior':ie,'cast_present':[],
                     'props':[],'lighting':[],'art_setup':[],'extras':[],
                     'context_facts':{'location':line,'day_night':line,'interior_exterior':line}}
            if current['elements'] and (location!=context['location'] or day!=context['day_night'] or ie!=context['interior_exterior']):
                change(line,'Location, interior/exterior, or time-of-day change',updates)
            elif not current['elements']:
                context={**context,**updates};new_scene(line,'Explicit production heading')
            emit('Scene Heading',line,start,end);speaker='';continue
        if RETURN.match(line):
            restored=saved_present or {**context,'temporal_context':'Present','sequence_type':'Scene'}
            change(line,'Return to present',restored);emit('Time Change',line,start,end);saved_present=None;continue
        if TIME.match(line):
            if context['temporal_context']=='Present':saved_present={**context}
            updates={'temporal_context':line,'sequence_type':'Scene'}
            if re.search(r'\bNIGHT\b',line,re.I):updates['day_night']='NIGHT'
            elif re.search(r'\b(?:DAY|MORNING)\b',line,re.I):updates['day_night']='DAY'
            change(line,'Explicit temporal shift',updates);emit('Time Change',line,start,end);continue
        if re.fullmatch(r'(?:DAY|NIGHT|DAWN|DUSK)(?:\s*[:.])?',line,re.I):
            day=line.rstrip(':.').upper()
            if day!=context['day_night']:change(line,'Explicit time-of-day change',{'day_night':day})
            emit('Time Change',line,start,end);continue
        if re.fullmatch(r'(?:INT\.?|EXT\.?|INTERIOR|EXTERIOR)',line,re.I):
            ie='INT' if line.upper().startswith('INT') else 'EXT'
            if ie!=context['interior_exterior']:change(line,'Explicit interior/exterior change',{'interior_exterior':ie})
            emit('Scene Heading',line,start,end);continue
        if END_SEQUENCE.match(line):
            emit('Transition',line,start,end)
            change('Return from '+context['sequence_type'],'End of distinct sequence',sequence_return or {'sequence_type':'Scene'})
            sequence_return=None;continue
        seq=SEQUENCE.match(line)
        if seq:
            sequence_return={**context};change(line,'Distinct montage/compilation sequence',{'sequence_type':seq[1].title()})
            emit('Montage',line,start,end)
            if seq[2] and not any(v[0] for v in lines[i+1:]):emit('Action',seq[2],start,end)
            continue
        named=re.match(r'^(SCENE(?:\s+\d+)?|SEQUENCE|LOCATION|SETUP)\s*[:–—-]\s*(.+)',line,re.I)
        if named:
            updates={'sequence_type':'Scene'}
            if named[1].upper()=='LOCATION':updates['location']=named[2]
            change(named[2],'Explicit scene/sequence/setup marker',updates);emit('Sequence Heading',line,start,end);continue
        natural=re.match(r'^(?:WE (?:CUT|MOVE) TO|CUT TO|AT)\s+(?:THE\s+)?(.+?)(?:\s*[-–—]\s*(DAY|NIGHT))?\.?$',line,re.I)
        if natural and not speaker and len(line.split())<14:
            change(line,'Explicit prose location cue',{'location':natural[1],'day_night':natural[2] or context['day_night'],
                   'interior_exterior':UNKNOWN,'cast_present':[],'props':[],'context_assumptions':['Interior/exterior for prose location requires confirmation']})
            emit('Scene Heading',line,start,end);continue
        kind=next((kind for pattern,kind in PREFIXES if re.match(pattern,line,re.I)),None)
        if kind:
            emit(kind,line,start,end);speaker='';speaker_start=None;has_spoken=False;continue
        if line.startswith('(') and line.endswith(')'):
            emit('Parenthetical',line,start,end,speaker,voice);continue
        label=LABEL.match(line)
        if label:
            speaker=label[1].strip();voice=bool(label[2]);speaker_start=start;has_spoken=False
            if label[3]:
                emit('Voice Over' if voice and 'V' in label[2].upper() else 'Dialogue',label[3],start,end,speaker,voice);has_spoken=True
            continue
        if (not speaker and line.isupper() and re.fullmatch(r"[A-Z][A-Z '\-]{1,30}(?: \([VO.S]+\))?",line)
            and len(line.split())<=3 and i+1<len(lines) and lines[i+1][0] and not ACTION.match(line)):
            speaker=re.sub(r'\s*\(.*\)','',line).title();voice='(' in line;speaker_start=start;has_spoken=False;continue
        bullet=bool(re.match(r'^(?:[-•*]|\d+[.)])\s+',line));action_line=re.sub(r'^(?:[-•*]|\d+[.)])\s+','',line)
        if ACTION.match(action_line) or bullet or line.startswith('['):
            kind='Reaction' if re.search(r'\b(?:freezes|flinches|recoils|stares in|gasps|reacts)\b',line,re.I) else 'Action'
            emit(kind,action_line,start,end);speaker='';speaker_start=None;has_spoken=False
        elif speaker:
            emit('Voice Over' if voice else 'Dialogue',line,speaker_start if not has_spoken and speaker_start is not None else start,end,speaker,voice);has_spoken=True
        else:emit('Action',line,start,end)
    push_scene()
    if not any(e['type'] not in ('Scene Heading','Sequence Heading','Time Change','Parenthetical','Transition') for e in elements):
        raise UserError('No usable screenplay content was found. Add dialogue, action, or title cards.')
    characters=list(dict.fromkeys(e['speaker'] for e in elements if e['speaker']))
    from .beats import build_beats, enrich_context
    chunks=[];remembered={}
    for s in scene_list:
        s['known_locations']=list(dict.fromkeys(x['location'] for x in scene_list if x['location']!=UNKNOWN))
        context_key=(s['location'],s.get('temporal_context','Present'))
        if context_key in remembered:
            previous=remembered[context_key]
            for field in ('costumes','lighting','art_setup','extras'):
                if not s['context'].get(field):s['context'][field]=previous.get(field,{} if field=='costumes' else [])
        enrich_context(s,characters);s['beats']=build_beats(s,raw)
        remembered[context_key]=s['context']
        group=[];size=0
        for beat in s['beats']:
            length=len(beat['source_script_block'])
            if group and size+length>6500:
                ids={n for b in group for n in b['source_ids']}
                chunks.append({**s,'beats':group,'elements':[e for e in s['elements'] if e['id'] in ids]});group=[];size=0
            group.append(beat);size+=length
        if group:
            ids={n for b in group for n in b['source_ids']}
            chunks.append({**s,'beats':group,'elements':[e for e in s['elements'] if e['id'] in ids]})
    return {'schema_version':2,'scenes':scene_list,'chunks':chunks,'elements':elements,'characters':characters}
