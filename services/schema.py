"""One normalized representation shared by the editor, providers and exporters."""
import hashlib
import json
import re
import uuid

class UserError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

SCHEMA_VERSION = 3
INTERNAL = {
    'scene': 'Scene Number', 'scene_name': 'Scene / Sequence Name', 'beat': 'Beat Number',
    'number': 'Shot Number', 'source_script_block': 'Source Script Block',
    'script': 'Script / Dialogue', 'shot_description': 'Shot Description',
    'shot_location': 'Shot Location', 'location_setup': 'Shot Location Requirement – Setup Wise',
    'shot_type_purpose': 'Shot Type / Purpose', 'shot_angle': 'Shot Angle',
    'shot_size': 'Shot Size', 'camera_movement': 'Camera Movement', 'fps': 'FPS / Speed Treatment',
    'cast': 'Cast', 'extras': 'Background / Extras', 'props': 'Props', 'costumes': 'Costume / Hair / Makeup',
    'lighting': 'Lighting & Light Changes', 'day_night': 'Day / Night',
    'interior_exterior': 'Interior / Exterior', 'art_setup': 'Art / Set Dressing',
    'design_elements': 'Design / Graphics / On-Screen Text', 'sfx': 'SFX / Practical Effects',
    'sound': 'Sound / Music / VO', 'vfx': 'VFX / Post Requirement',
    'production_requirements': 'Production Requirements', 'continuity': 'Continuity Notes',
    'reference': 'Reference', 'assumptions': 'Assumptions / Confirmation Required',
}
PRODUCTION = {
    'number':'SHOT','day_int_ext':'DAY/NIGHT + INT/EXT','visuals':'VISUALS',
    'size_angle':'SHOT SIZE / SHOT ANGLE','camera_movement':'MOVEMENT','shot_location':'LOCATION',
    'equipment':'EQUIPMENT','fps':'FPS','shot_description':'SHOT DESCRIPTION','lighting':'LIGHTING',
    'script':'SCRIPT / DIALOGUE','notes':'NOTES','clip_no':'CLIP NO.',
    'cast':'CAST','props':'PROPS','costumes':'COSTUME / HAIR / MAKEUP','art_graphics':'ART / SET / GRAPHICS',
    'production_requirements':'PRODUCTION REQUIREMENTS','assumptions':'ASSUMPTIONS / CONFIRMATION REQUIRED',
}
METADATA = {'client':'Project / Client','director':'Director','dop':'DoP','platform':'Platform',
            'location':'Location','date':'Date','duration':'Duration','aspect_ratio':'Aspect Ratio','reference':'Reference'}
IDENTITY_FIELDS = ['scene','scene_name','beat','source_script_block']
TRACE_FIELDS = ['source_spans','source_ids','source_order','source_provenance','beat_name','beat_reason',
                'scene_context','temporal_context','sound_cues','sfx_cues','vfx_cues','speed_treatment',
                'visual_treatment','facts','assumed_fields','production_order','coverage_count','coverage_label','group_reason','representative_shot','beat_ids','dialogue_present']
PLAN_FIELDS = ['script', 'shot_description', 'shot_purpose', 'shot_size', 'shot_angle',
               'camera_movement', 'cast', 'props', 'shot_type', 'shot_location',
               'day_night', 'interior_exterior', 'scene_name', 'beat', 'source_script_block',
               'visuals','equipment','fps','lighting','notes','costumes','art_graphics','production_requirements','assumptions','clip_no']
ALIASES = {'visual_action': 'shot_description', 'suggested_shot_size': 'shot_size',
           'suggested_angle': 'shot_angle', 'suggested_camera_movement': 'camera_movement',
           'characters_visible': 'cast', 'props_visible': 'props', 'relevant_dialogue': 'script',
           'scene_number': 'scene', 'shot_number': 'number', 'beat_number':'beat',
           'source_block':'source_script_block', 'scene_sequence_name':'scene_name',
           'background_extras':'extras','costume_hair_makeup':'costumes','art_set_dressing':'art_setup',
           'sfx_practical_effects':'sfx','sound_music_vo':'sound','vfx_post_requirement':'vfx',
           'continuity_notes':'continuity','fps_speed_treatment':'fps'}

def text(value):
    if isinstance(value, list):
        return ', '.join(str(v) for v in value)
    return '' if value is None else str(value).strip()

def normalize(row):
    if not isinstance(row, dict):
        raise UserError('Each shot must be an object.')
    out = dict(row)
    for old, new in ALIASES.items():
        if not out.get(new) and old in out:
            out[new] = out[old]
        out.pop(old, None)
    for key in set(PLAN_FIELDS) | set(PRODUCTION) | set(INTERNAL) | {'scene', 'number', 'id','size_movement','shot_type','shot_purpose'}:
        out[key] = str(out.get(key) or '') if key=='source_script_block' else text(out.get(key))
    out['id'] = out['id'] or uuid.uuid4().hex
    for combined,left,right in [('size_angle','shot_size','shot_angle'),('day_int_ext','day_night','interior_exterior')]:
        if out[combined]:
            values=out[combined].split(' / ',1);out[left]=values[0];out[right]=values[1] if len(values)>1 else ''
    out['scene'] = out['scene'] or '1'
    parts=out['number'].split('.')
    out['beat']=out['beat'] or ('.'.join(parts[:2]) if len(parts)>=3 else out['scene']+'.1')
    out['scene_name']=out['scene_name'] or out['shot_location'] or f'Scene {out["scene"]}'
    if not out['source_script_block']:
        out['source_script_block']=out['script'] or out['shot_description']
        out['source_provenance']=out.get('source_provenance') or 'Legacy/imported row text; original screenplay formatting unavailable'
    if out['size_movement'] and (not out['shot_size'] or not out['camera_movement']):
        framing=out['size_movement'].split(' / ',1)
        out['shot_size']=out['shot_size'] or framing[0]
        out['camera_movement']=out['camera_movement'] or (framing[1] if len(framing)>1 else '')
    out['size_movement']=' / '.join(filter(None,[out['shot_size'],out['camera_movement']]))
    out['shot_type_purpose']=out['shot_type_purpose'] or ' / '.join(filter(None,[out['shot_type'],out['shot_purpose']]))
    out['schema_version']=SCHEMA_VERSION
    if 'existing' in out and not isinstance(out['existing'],dict):
        raise UserError('Imported production fields must be an object.')
    return out

def shot_interval(value):
    """Single numbers, legacy dotted IDs and deliberate labelled coverage ranges."""
    match=re.fullmatch(r'(\d+(?:\.\d+)*)(?:\s*[-–—]\s*(\d+))?(?:\s+([^\r\n]+))?',text(value))
    if not match:raise UserError('Use a shot number or range, such as 28 or 29–41 Process.')
    start=match[1];end=match[2]
    if end and ('.' in start or int(end)<int(start)):raise UserError('Shot ranges must have an ending number at least as large as their start.')
    return start,end,match[3] or ''

def production_view(row):
    """Explicit projection: richer source/continuity data stays in the project."""
    r=normalize(row)
    def useful(v):return text(v) not in ('','None specified','Not applicable','Normal')
    r['day_int_ext']=r['day_int_ext'] or ' / '.join(filter(None,[r['day_night'],r['interior_exterior']]))
    r['size_angle']=r['size_angle'] or ('Full Frame Graphic' if is_graphic(r) else ' / '.join(filter(None,[r['shot_size'],r['shot_angle']])))
    if not r['notes'] and row.get('schema_version',0)<3:
        r['notes']='\n'.join(f'{label}: {r[k]}' for k,label in [('sfx','SFX'),('sound','Sound / VO'),('vfx','Post'),('continuity','Continuity')] if useful(r.get(k)))
    if not r['art_graphics'] and row.get('schema_version',0)<3:r['art_graphics']='; '.join(dict.fromkeys(r[k] for k in ('art_setup','design_elements') if useful(r[k])))
    return {k:r[k] for k in PRODUCTION}

def validate_plan(rows):
    if not isinstance(rows, list) or not rows or len(rows) > 300:
        raise UserError('Add between 1 and 300 shots before continuing.')
    rows = [normalize(r) for r in rows]
    if len({r['id'] for r in rows}) != len(rows):
        raise UserError('Shot identifiers must be unique. Duplicate shots using the editor.')
    numbers = set();intervals=[]
    for row in rows:
        first,last,_=shot_interval(row['number'])
        if '.' not in first:
            lo,hi=int(first),int(last or first)
            if any(scene==row['scene'] and lo<=b and hi>=a for scene,a,b in intervals):raise UserError('Shot numbers or ranges overlap in this scene. Edit or renumber the plan.')
            intervals.append((row['scene'],lo,hi))
        if not re.fullmatch(r'\d+',row['scene']) or not re.fullmatch(r'\d+\.\d+',row['beat']) or row['beat'].split('.')[0]!=row['scene']:
            raise UserError('Use a numeric scene and a matching beat such as Scene 2, Beat 2.1.')
        identity=(row['scene'],row['number'])
        if identity in numbers:
            raise UserError('Shot numbers must be unique. Use Renumber shots to repair them.')
        numbers.add(identity)
        if not row['script'] and not row['shot_description']:
            raise UserError('Each shot needs script text or a visual description.')
        if any(len(text(row.get(k))) > 15000 for k in PLAN_FIELDS):
            raise UserError('A shot field is too long. Split this into smaller shots.')
    return rows

def fingerprint(plan):
    payload = [{k: r.get(k, '') for k in ['id','scene','number',*PLAN_FIELDS,*TRACE_FIELDS,'existing']} for r in plan]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def numeric_key(row):
    def parts(v): return tuple(int(n) for n in re.findall(r'\d+',text(v)))
    if isinstance(row.get('production_order'),(int,float)):return (0,row['production_order'])
    return (1,parts(row.get('scene')),parts(row.get('number')))

def ordered(rows):
    return sorted(rows, key=numeric_key)

def is_graphic(row):
    return any(s in row.get('shot_type', '').lower() for s in ('graphic', 'title', 'stage card'))
