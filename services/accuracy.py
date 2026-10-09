"""Deterministic source/production preflight. Semantic judgments remain review warnings."""
import re
from .schema import PRODUCTION, production_view, shot_interval, UserError
from .screenplay import analyze

REQUIRED=('number','day_int_ext','size_angle','camera_movement','shot_location','equipment','fps','shot_description','lighting','script','cast','props','costumes')

def compact(value):
    return re.sub(r'\s+',' ',str(value or '')).strip().strip('"“”').casefold()

def audit(rows, plan=None, source_script=None):
    if source_script is not None and not isinstance(source_script,str):raise UserError('Source script must be text.')
    errors=[];warnings=[]
    def issue(level,code,message,row=None):
        item={'code':code,'message':message}
        if row:item.update(shot=row['number'],row_id=row['id'])
        (errors if level=='error' else warnings).append(item)
    previous_scene=0;previous_end=0;seen=set();numbers=set();signatures=set()
    for row in rows:
        view=production_view(row)
        for key in REQUIRED:
            if not str(view[key]).strip():issue('error','required_field',f'{PRODUCTION[key]} is empty. Enter a value, N/A, or Confirmation Required.',row)
        description=compact(row.get('shot_description'))
        if description in ('','new shot — describe what the camera sees','confirmation required') or re.fullmatch(r'[\w .’\'-]{1,40}:',description):
            issue('error','empty_setup','Describe a shootable action or visual subject.',row)
        scene=int(row['scene'])
        if scene<previous_scene:issue('error','scene_order','Scene order must follow the script.',row)
        previous_scene=scene
        first,last,label=shot_interval(row['number'])
        if first in numbers:issue('error','duplicate_number','Duplicate shot number.',row)
        numbers.add(first)
        if '.' not in first:
            start,end=int(first),int(last or first)
            if start<=previous_end:issue('error','shot_overlap','Shot numbers or ranges overlap or move backwards.',row)
            elif previous_end and start!=previous_end+1:issue('warning','number_gap',f'Numbering jumps from {previous_end} to {start}; confirm the intentional gap.',row)
            previous_end=end
        if row['id'] in seen:issue('error','duplicate_id','Duplicate shot identity.',row)
        seen.add(row['id'])
        signature=(row['scene'],compact(row['shot_description']),compact(row['size_angle']),compact(row['camera_movement']),tuple(row.get('source_ids',[])))
        if signature in signatures:issue('warning','duplicate_setup','This setup repeats another row; confirm that the extra coverage is needed.',row)
        signatures.add(signature)
        if last and int(last)>int(first) and not row.get('group_reason') and not row.get('coverage_label'):
            issue('warning','range_reason','Explain why this range belongs to one coverage block.',row)
        if row.get('assumptions'):issue('warning','assumptions',row['assumptions'],row)
        unresolved=[PRODUCTION[k] for k in REQUIRED if re.search(r'confirmation required|\bTBD\b|to confirm',view[k],re.I)]
        if unresolved:issue('warning','unresolved','Confirm: '+', '.join(unresolved)+'.',row)
        # Explicit source claims can be checked; absence of evidence is a warning, not a fact.
        evidence=compact(row.get('source_script_block','')+' '+str(row.get('scene_context',{})))
        existing=row.get('existing',{})
        for key in ('shot_location','props','equipment'):
            value=compact(view[key])
            confirmed=all(part.strip() in evidence for part in value.split(','))
            if value and value not in ('none','none specified','n/a','not applicable') and not confirmed and key not in existing and not re.search(r'confirm|proposed|assum|unspecified|not specified|\bTBD\b',value,re.I):
                issue('warning','unsupported_detail',f'{PRODUCTION[key]}: “{view[key]}” is not confirmed verbatim in the source. Verify this production choice.',row)
        size=compact(row.get('shot_size'))
        desc=compact(row.get('shot_description'))
        families={'ecu':'extreme','extreme close-up':'extreme','cu':'close','close-up':'close','mcu':'medium-close','medium close-up':'medium-close','ms':'medium','medium':'medium','ws':'wide','wide':'wide'}
        explicit=re.match(r'(ECU|MCU|CU|MS|WS|extreme close[- ]up|medium close[- ]up|close[- ]up|wide|medium)\b',desc,re.I)
        if explicit and families.get(explicit[1].lower().replace('close up','close-up'))!=families.get(size) and size in families:
            issue('error','framing_conflict','Shot size conflicts with the opening framing instruction in SHOT DESCRIPTION.',row)
    source_verified=False
    if source_script:
        parsed=analyze(source_script);elements={e['id']:e for e in parsed['elements']}
        covered=set()
        for row in rows:
            ids=row.get('source_ids',[]);spans=row.get('source_spans',[])
            manual=row.get('source_provenance','').startswith('Manual')
            if manual:issue('warning','manual_source','Manual addition has no screenplay source.',row);continue
            if not ids or not spans:
                issue('error','missing_trace','This script-derived row has no source references.',row);continue
            try:
                valid=all(type(s['start']) is int and type(s['end']) is int and 0<=s['start']<s['end']<=len(source_script) for s in spans)
                exact=''.join(source_script[s['start']:s['end']] for s in spans)
            except (KeyError,TypeError):valid=False;exact=''
            if not valid or exact!=row.get('source_script_block'):
                issue('error','source_changed','Source text no longer matches the supplied screenplay. Re-analyze or restore the original source.',row)
            for source_id in ids:
                e=elements.get(source_id)
                if e is None or not any(s.get('start',-1)<=e['source_start'] and s.get('end',-1)>=e['source_end'] for s in spans):
                    issue('error','source_identity','Source identity does not match the stored character spans.',row);continue
                covered.add(source_id)
                if str(e['scene'])!=str(row['scene']):issue('error','source_scene','The source belongs to a different scene.',row)
                if e['type'] in ('Dialogue','Voice Over'):
                    text=compact(e['text']);mapped=compact(row.get('script',''))
                    if text not in mapped:
                        # Motivated reverse angles can share a beat, but at least one shot must retain the full line.
                        other=any(source_id in r.get('source_ids',[]) and text in compact(r.get('script','')) for r in rows)
                        if not other:issue('error','dialogue_missing','Dialogue or voice-over was changed or omitted from SCRIPT / DIALOGUE.',row)
            # Any new speaker-labelled sentence must originate in this row's referenced elements.
            allowed=[compact((elements[n]['speaker']+': ' if elements[n]['speaker'] else '')+elements[n]['text']) for n in ids if n in elements]
            for line in str(row.get('script','')).splitlines():
                if re.match(r'^[A-Za-z][\w .’\'-]{0,40}:',line) and compact(line) not in allowed:
                    # Production labels are source text too; compact comparison permits whitespace-only edits.
                    if compact(line) not in compact(row.get('source_script_block')):
                        issue('error','dialogue_invented','SCRIPT / DIALOGUE contains a speaker/label line absent from this source block.',row)
                elif compact(line) and compact(line) not in ('n/a','not applicable') and not any(compact(line) in a for a in allowed) and compact(line) not in compact(row.get('source_script_block')):
                    issue('error','script_unmapped','SCRIPT / DIALOGUE contains text absent from the source. Restore the original wording.',row)
        important={n for n,e in elements.items() if e['type'] not in ('Scene Heading','Sequence Heading','Time Change','Parenthetical')}
        for missing in sorted(important-covered):
            e=elements[missing]
            issue('error','uncovered_beat',f'Scene {e["scene"]}: uncovered {e["type"]}: {e["text"][:140]}')
        source_verified=not any(e['code'] in ('source_changed','missing_trace','source_identity','source_scene','uncovered_beat','dialogue_missing','dialogue_invented','script_unmapped') for e in errors)
    else:issue('warning','source_unavailable','Full original script is unavailable. Coverage is checked against the reviewed rows only; confirm completeness manually.')
    return {'ok':not errors,'errors':errors,'warnings':warnings,'source_verified':source_verified,'rows':len(rows),'scenes':len({r['scene'] for r in rows}),'groups':sum(bool(r.get('coverage_label') or shot_interval(r['number'])[1]) for r in rows)}
