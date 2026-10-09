"""Meaningful beat boundaries and shared scene facts, independent of AI providers."""
import re
from copy import deepcopy
from .screenplay import source_block, UNKNOWN

GRAPHICS={'Title Card','Stage Card','On-Screen Text'}
METADATA={'Scene Heading','Sequence Heading','Time Change','Montage'}
AUDIO={'SFX','Music Cue'}
SPECIAL={'Reaction','Reveal','Insert','POV','Split Screen','Split Screen Panel','Speed Treatment','VFX','Camera Direction','Coverage'}
PROP_WORDS=r'laptop|phone|campaign brief|brief|cup|glass|bag|book|letter|bike keys|keys|key|envelope|notebook|ring|bottle|helmet|bike|saucepan|stove|plate|suitcase|photo|photograph|gun|knife|box|watch|bicycle|car|mug|folder|tea leaves|water|lamp'

def physical_props(value):
    found={}
    screen_setup=bool(re.search(r'\bsame screen setup\b',value,re.I))
    for m in re.finditer(r'\b(?:'+PROP_WORDS+r')\b',value,re.I):
        name=m.group(0);key=name.casefold()
        # A document opened in a screen workflow is content, not a physical prop.
        if screen_setup and key in ('brief','campaign brief','letter','book','photo','photograph') and not re.search(r'\b(?:printed|physical|paper)\s+'+re.escape(key)+r'\b',value,re.I):continue
        found.setdefault(key,name)
    return list(found.values())

def enrich_context(scene,characters):
    ctx=scene['context'];ctx['location']=scene['location'];ctx['day_night']=scene['day_night'];ctx['interior_exterior']=scene['interior_exterior']
    visual=[e for e in scene['elements'] if e['type'] not in GRAPHICS|AUDIO|METADATA|{'Dialogue','Voice Over','Parenthetical','Transition'}]
    names=list(dict.fromkeys([e['speaker'] for e in scene['elements'] if e['speaker'] and not e['heard_only']]+[
        name for name in characters if any(re.search(r'\b'+re.escape(name)+r'\b',e['text'],re.I) for e in visual)]))
    for e in visual:
        action=re.sub(r'^(?:(?:ECU|MCU|CU|MS|WS|WIDE|CLOSE[- ]UP|MEDIUM|REACTION)\s*(?:of\s+|:\s*))','',e['text'],flags=re.I)
        match=re.match(r'^([A-Z][\w\-]+)\s+(?:slams|opens|enters|picks|puts|turns|walks|runs|holds|wears|is wearing|grabs|drops|stares|freezes|flinches|placing|lifting|sets|smiles)',action)
        if match and match[1].lower() not in ('the','a','an','he','she','they','we','camera') and match[1] not in names:names.append(match[1])
    ctx['cast_present']=names
    ctx['props']=list(dict.fromkeys(p for e in visual for p in physical_props(e['text'])))
    # Store a forward-only snapshot after every source element. Later wardrobe or
    # lighting changes must never leak backwards into an earlier shot.
    running=deepcopy(ctx);running['costumes']=dict(ctx.get('costumes',{}));running['props']=[]
    running['lighting']=list(ctx.get('lighting',[]));running['art_setup']=list(ctx.get('art_setup',[]));running['extras']=list(ctx.get('extras',[]))
    scene['initial_context']=deepcopy(running)
    for e in scene['elements']:
        if e not in visual:
            e['context']=deepcopy(running);continue
        for name in names:
            m=re.search(r'\b'+re.escape(name)+r'\s+(?:wears|is wearing|changes into)\s+([^.!?]+)',e['text'],re.I)
            if m:running['costumes'][name]=re.split(r'\s+and\s+(?:holds|walks|runs|turns|sits|stands|opens|looks|sets|puts|picks|takes|grabs|drops)\b',m[1],maxsplit=1,flags=re.I)[0].strip()
        if re.search(r'\b(?:light|lighting|sunlight|moonlight|fluorescent|neon|candle|lamp)\b',e['text'],re.I):running['lighting']=[e['text']]
        if re.search(r'\b(?:walls?|furniture|dressing|decor|posters?|curtains?|furnished)\b|^ART:',e['text'],re.I):running['art_setup']=[e['text']]
        if re.search(r'\b(?:crowd|extras|passersby|background actors|commuters)\b',e['text'],re.I):running['extras']=[e['text']]
        if re.match(r'^(?:HAIR|MAKEUP)\s*:',e['text'],re.I):running['hair_makeup']=e['text']
        running['props']=list(dict.fromkeys(running['props']+physical_props(e['text'])))
        e['context']=deepcopy(running)
        if scene['sequence_type'] in ('Montage','Compilation'):
            # Each montage setup gets its own location; do not carry a previous
            # setup's location into a visually different one without evidence.
            known=next((loc for loc in scene.get('known_locations',[]) if re.search(r'\b'+re.escape(loc)+r'\b',e['text'],re.I)),None)
            e['context']['location']=known or UNKNOWN
            if known:e['context']['context_assumptions']=[f'Location inferred from the named {known} in this setup']
    scene['context']=running

def build_beats(scene,raw):
    beats=[];current=[];pending=[];kind='Dialogue exchange';reason='Continuous exchange in a shared setup'
    montage=scene['sequence_type'] in ('Montage','Compilation')
    def flush():
        nonlocal current
        if not current:return
        if all(e['type'] in METADATA|{'Parenthetical','Transition'} for e in current):pending.extend(current);current=[];return
        block,spans=source_block(raw,current);n=len(beats)+1
        beats.append({'id':f'{scene["number"]}.{n}','number':f'{scene["number"]}.{n}',
            'name':kind,'reason':reason,'source_ids':[e['id'] for e in current],
            'source_script_block':block,'source_spans':spans,'elements':current.copy()})
        current=[]
    for e in scene['elements']:
        t=e['type']
        if t in METADATA:pending.append(e);continue
        if t=='Transition':
            if current:current.append(e)
            elif beats:
                b=beats[-1];b['elements'].append(e);b['source_ids'].append(e['id']);b['source_script_block'],b['source_spans']=source_block(raw,b['elements'])
            else:pending.append(e)
            continue
        if t in AUDIO or t=='Parenthetical':(current if current else pending).append(e);continue
        if t=='Production Note' and not re.search(r'\b(?:changes?|shift|dims?|switch|new setup)\b',e['text'],re.I):
            (current if current else pending).append(e);continue
        if t in GRAPHICS:
            flush();kind='Graphic / title moment';reason='Separate graphic production unit';current=pending+[e];pending=[];flush();continue
        if t=='Split Screen' and re.fullmatch(r'SPLIT[- ]SCREEN\s*:?\s*',e['text'],re.I):
            flush();pending.append(e);continue
        significant=t=='Action' and bool(re.search(r'\b(?:slams?|shatters?|rips?|explodes?|reveals?|bursts?|tears?|changes into|lighting changes|lights dim)\b',e['text'],re.I))
        boundary=t in SPECIAL or significant or t=='Production Note' or (montage and t in ('Action','Dialogue','Voice Over'))
        if t=='Split Screen Panel' and any(x['type']=='Split Screen Panel' for x in current):boundary=False
        if boundary:
            flush();kind=('Montage setup' if montage else t if not significant else 'Significant physical action')
            reason='Distinct visual setup in the sequence' if montage else 'Explicit change in visual subject, framing, treatment, or significant action'
            if t=='Split Screen Panel':kind='Split-screen panel';reason='Separate camera plate for a shared split-screen composition'
        if not current and not boundary:
            kind='Dialogue exchange' if t in ('Dialogue','Voice Over') else 'Physical action'
            reason='Continuous exchange in a shared setup' if t in ('Dialogue','Voice Over') else 'Related actions within one production setup'
        if current and sum(len(x['text']) for x in current)+len(e['text'])>2400:
            flush();kind='Extended beat continuation';reason='Long passage; separate coverage proposed at a complete source-block boundary'
        current.extend(pending);pending=[];current.append(e)
    flush()
    if pending:
        if beats:
            b=beats[-1];b['elements'].extend(pending);b['source_ids'].extend(e['id'] for e in pending)
            b['source_script_block'],b['source_spans']=source_block(raw,b['elements'])
        elif any(e['type'] in AUDIO for e in pending):
            current=pending;pending=[];kind='Audio / post cue';reason='Independent sound production unit, no visible speaker inferred';flush()
    return beats

def shootable_units(beat):
    """A split-screen beat needs separate camera plates, with shared beat identity."""
    panels=[e for e in beat['elements'] if e['type']=='Split Screen Panel']
    if len(panels)<2:return [beat]
    units=[];prefix=[];group=[]
    for e in beat['elements']:
        if e['type']=='Split Screen Panel':
            if group:units.append(group)
            group=[e]
        elif group:group.append(e)
        else:prefix.append(e)
    if group:units.append(group)
    result=[];origin=beat['source_spans'][0]['start']
    for index,unit in enumerate(units):
        if index==0:unit=prefix+unit
        start=min(e['source_start'] for e in unit);end=max(e['source_end'] for e in unit)
        result.append({**beat,'elements':unit,'source_ids':[e['id'] for e in unit],
            'source_script_block':beat['source_script_block'][start-origin:end-origin],
            'source_spans':[{'start':start,'end':end}],
            'reason':'Separate camera plate for a shared split-screen composition'})
    return result
