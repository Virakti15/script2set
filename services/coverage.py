"""Coverage blocks keep explicit counts; unknown coverage is never assigned invented counts."""
import re
from .schema import shot_interval, text

def coverage_info(source):
    # A number range is evidence only when marked as a shot identifier.
    span=re.search(r'\bSHOTS?\s+(\d+)\s*[-–—]\s*(\d+)',source,re.I)
    process=bool(re.search(r'\bprocess\b|workflow|interface coverage',source,re.I))
    group=bool(span or re.search(r'\bB[- ]ROLL\b|\b(?:multiple|various|several|two|\d+)\s+(?:\w+\s+){0,3}(?:shots|close-ups|inserts)\b|\bshots of\b|\bcoverage block\b',source,re.I))
    count=None
    if span and int(span[2])>=int(span[1]):count=int(span[2])-int(span[1])+1
    if not count:
        m=re.search(r'\b(\d+|two|three|four|five)\s+(?:\w+\s+){0,3}(?:shots|close-ups|inserts)\b',source,re.I)
        if m:count=int(m[1]) if m[1].isdigit() else {'two':2,'three':3,'four':4,'five':5}[m[1].lower()]
        m=re.search(r'\b(?:shots?|POV)\s*[x×]\s*(\d+)\b',source,re.I)
        if m:count=int(m[1]);group=True
    return {'group':group,'count':count,'label':'Process' if process else 'Coverage' if re.search(r'\bPOV\b',source,re.I) else 'B-roll' if re.search(r'B[- ]ROLL|shots of|vendors|lanes',source,re.I) else 'Coverage'}

def assign_production_numbers(rows,offset=0,previous=None):
    cursor=offset+1
    if previous:
        start,end,_=shot_interval(previous[-1]['number'])
        if '.' not in start:cursor=int(end or start)+1
    for index,row in enumerate(rows):
        info=coverage_info(row['source_script_block'])
        count=info['count'] if info['group'] else 1
        if count and count>1000:count=None
        row['coverage_count']=count or 0
        row['coverage_label']=info['label'] if info['group'] else ''
        row['group_reason']='Related source-directed coverage within this production setup' if info['group'] else ''
        row['number']=f'{cursor}–{cursor+count-1} {info["label"]}' if count and count>1 else f'{cursor} {info["label"]}' if info['group'] else str(cursor)
        row['representative_shot']=str(cursor)
        row['production_order']=offset+index
        row['beat_ids']=row.get('beat_ids') or [row['beat']]
        if info['group']:
            row['shot_type']=info['label']+' coverage group' if info['label']!='Coverage' else 'Coverage group'
            row['shot_purpose']=row['group_reason']
            if not count:row['assumptions']='Coverage count to confirm; no fixed shot range assigned.'
        cursor+=count or 1
    return rows

def safe_group(beats):
    """Reject multi-beat model groups unless production requirements agree."""
    if len(beats)<2:return True
    keys=[]
    for b in beats:
        ctx=b['elements'][-1].get('context',{})
        value=b['source_script_block']
        if not coverage_info(value)['group']:return False
        if any(e['type'] in ('Dialogue','Reaction','Reveal','Split Screen Panel','Title Card','Stage Card','Speed Treatment') for e in b['elements']):return False
        # Do not collapse unresolved setups or incompatible camera instructions.
        if ctx.get('location') in (None,'Confirmation Required'):return False
        camera=re.findall(r'\b(?:ECU|MCU|MS|WS|CU|wide|close-up|static|handheld|pan|tilt|POV|top|low|tracking|dolly|gimbal)\b',value,re.I)
        keys.append((ctx.get('location'),str(ctx.get('lighting')),str(ctx.get('costumes')),str(ctx.get('cast_present')),tuple(x.lower() for x in camera)))
    return all(k==keys[0] for k in keys)
