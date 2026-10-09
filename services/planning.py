"""Scene → beat → shootable unit; provider output is constrained by source evidence."""
import re
from .schema import normalize, is_graphic, PLAN_FIELDS, PRODUCTION, INTERNAL, IDENTITY_FIELDS, TRACE_FIELDS, UserError, text, production_view
from .coverage import assign_production_numbers, coverage_info, safe_group
from .providers import complete, provider_name
from .beats import GRAPHICS, METADATA, AUDIO, physical_props, shootable_units
from .screenplay import UNKNOWN, SCENE

PLAN_PROMPT='''You are a director and first AD. Return {"shots":[...]}.
Each row is ONE independently shootable camera/production unit, NOT a line, sentence, paragraph or speaker turn.
Each shot contains beat (provided beat number), source_ids (provided integer element IDs), shot_description,
shot_purpose, shot_size, shot_angle, camera_movement, cast (visible only), props (physical only), shot_type.
Keep scene and beat order. Within a beat, use master/two-shot for a continuous exchange; multiple coverage rows
are allowed only with a motivated change of subject, framing, angle, movement, reaction, action, insert, reveal,
speed, POV, split-screen panel, distinct montage setup, or practical/VFX execution. State that motivation in shot_purpose.
Never create variety for its own sake. Tiny related movements stay together. Long dialogue is not one row per line.
Respect supplied scene/time/continuity facts. Heard-only VO/OS speakers are not visible cast.
Retain all non-heading source elements including final cards and sound cues. Cards remain separate graphic rows,
Full Screen Graphic / Static / cast None / props None. Never combine graphics with live action.
Do not invent facts or physical props from figurative dialogue. Unknown facts: Confirmation Required.
The supplied beats/draft are conservative proposals for human review. Source Script Block is assigned by the server;
do not rewrite it. A row may also be a deliberately grouped process, montage or B-roll coverage block.
Do not expand each process insert into a repetitive row. Group only a shared location, lighting, cast, camera setup,
visual objective and production requirement. Return beat_ids when grouping adjacent supplied beats, plus source_ids
for every included source element. Never invent a coverage count. Explicit source counts become shot ranges on the server.
Keep supplied beat identities, but refine their coverage into shootable rows where justified.'''

def elements_for(beat):
    return [e for e in beat['elements'] if e['type'] not in METADATA]

def description(group,size,visible):
    actions=[e['text'] for e in group if e['type'] not in AUDIO|GRAPHICS|{'Dialogue','Voice Over','Parenthetical','Transition','Production Note'}]
    if actions:
        action=' '.join(actions)
        return action if re.match(r'^(?:ECU|MCU|CU|MS|WS|WIDE|CLOSE[- ]UP|MEDIUM)\b',action,re.I) else f'{size}: '+action
    speech=next((e['text'] for e in group if e['type'] in ('Dialogue','Voice Over')),'')
    if visible:return f'{size} of '+', '.join(visible)+f' through the exchange beginning “{speech[:160]}”'
    return 'Visual subject requires confirmation; accompany the off-screen sound or voice-over.'

def draft_plan(scene,offset=0):
    shots=[];shot_counts={}
    beats=scene.get('beats',[])
    if not beats:raise UserError('This scene has no shootable beats. Re-analyze the screenplay.')
    for beat in [unit for b in beats for unit in shootable_units(b)]:
        group=elements_for(beat);types={e['type'] for e in group}
        if not group:continue
        ctx=beat['elements'][-1].get('context',scene.get('context',{}))
        visible=list(dict.fromkeys(e['speaker'] for e in group if e['speaker'] and not e.get('heard_only')))
        actions=' '.join(e['text'] for e in group if e['type'] not in AUDIO|GRAPHICS|{'Dialogue','Voice Over','Parenthetical','Transition'})
        for name in ctx.get('cast_present',[]):
            if re.search(r'\b'+re.escape(name)+r'\b',actions,re.I) and name not in visible:visible.append(name)
        size='Two Shot' if len(visible)==2 else 'Master Shot' if len(visible)>2 else 'Medium' if visible else 'Wide'
        angle='Eye level';movement='Static';shot_type='Live Action';treatment='Normal';speed='Normal speed'
        if 'Insert' in types:size='Close-Up';shot_type='Insert / Detail'
        if 'Reaction' in types:size='Close-Up';shot_type='Reaction'
        if 'Reveal' in types:shot_type='Reveal'
        if 'POV' in types:
            angle='POV';shot_type='POV';treatment='POV'
            if re.search(r'\bphone POV\b',actions,re.I):size='Close-Up'
            visible=[name for name in visible if not re.search(r'\bPOV\s*:\s*'+re.escape(name)+r'(?:\s+sees|[’\']s)',actions,re.I)]
        if types & {'Split Screen','Split Screen Panel'}:shot_type='Split Screen';treatment='Split-screen composite; shoot each panel separately'
        if 'VFX' in types:shot_type='Effects plate / VFX'
        if scene.get('sequence_type') in ('Montage','Compilation'):shot_type=scene['sequence_type']+' setup'
        if re.search(r'\b(?:slow[- ]motion|slow[- ]mo)\b',actions,re.I):speed='Slow motion; capture FPS / playback rate: Confirmation Required'
        if re.search(r'\b(?:normal speed|real time)\b',actions,re.I):speed='Normal speed'
        for pattern,value in [(r'\bEXTREME CLOSE[- ]UP\b','Extreme Close-Up'),(r'\bCLOSE[- ]UP\b','Close-Up'),(r'\bWIDE SHOT\b','Wide'),(r'\bTWO SHOT\b','Two Shot'),(r'\bMASTER SHOT\b','Master Shot')]:
            if re.search(pattern,actions,re.I):size=value;break
        short=re.search(r'\b(ECU|MCU|CU|MS|WS)\b',actions,re.I)
        if short:size=short[1].upper()
        if re.match(r'^WIDE\s*:',actions,re.I):size='Wide'
        if re.search(r'\b(?:top|overhead)\b',actions,re.I):angle='Top'
        for pattern,value in [(r'\bHIGH ANGLE\b','High angle'),(r'\bLOW ANGLE\b','Low angle'),(r'\bTOP SHOT\b','Top shot'),(r'\bOTS|OVER[- ]THE[- ]SHOULDER\b','Over-the-shoulder')]:
            if re.search(pattern,actions,re.I):angle=value;break
        for pattern,value in [(r'\b(?:TRACK|TRACKING)\b','Tracking'),(r'\bDOLLY\b','Dolly'),(r'\bPAN\b','Pan'),(r'\bTILT\b','Tilt')]:
            if re.search(pattern,actions,re.I):movement=value;break
        for pattern,value in [(r'\bhandheld\b','Handheld'),(r'\bpush[- ]in\b','Push In'),(r'\bpull[- ]out\b','Pull Out'),(r'\bwhip pan\b','Whip Pan'),(r'\blocked off\b','Locked Off')]:
            if re.search(pattern,actions,re.I):movement=value;break
        graphic=bool(types&GRAPHICS)
        audio_only=not any(e['type'] not in AUDIO|{'Voice Over','Parenthetical','Transition'} for e in group)
        if graphic:
            shot_type='Title Card / Graphic';size='Full Screen Graphic';angle='Not applicable';movement='Static';visible=[]
        if audio_only:
            shot_type='Audio / Post';size='Not applicable';angle='Not applicable';movement='Not applicable';visible=[]
        src='\n'.join((e['speaker']+': ' if e['speaker'] else '')+e['text'] for e in group if e['type'] not in AUDIO|{'Parenthetical','Transition'})
        shot_counts[beat['number']]=shot_counts.get(beat['number'],0)+1
        row={'scene':scene['number'],'scene_name':scene.get('name',scene['heading']), 'beat':beat['number'],
            'number':beat['number']+'.'+str(shot_counts[beat['number']]),'source_script_block':beat['source_script_block'],
            'source_spans':beat['source_spans'],'source_ids':beat['source_ids'],
            'source_order':min(e['source_start'] for e in beat['elements']), 'source_provenance':'Original screenplay, exact character spans',
            'beat_name':beat['name'],'beat_reason':beat['reason'],'scene_context':ctx,
            'temporal_context':scene.get('temporal_context','Present'),'script':src or '\n'.join(e['text'] for e in group),
            'shot_description':('Full-screen typography: '+' / '.join(e['text'] for e in group if e['type'] in GRAPHICS)) if graphic else description(group,size,visible),
            'shot_purpose':beat['reason'],'shot_size':size,'shot_angle':angle,'camera_movement':movement,
            'cast':'None' if graphic or audio_only or (not visible and (types&{'Insert','POV'} or (types&{'Camera Direction','Coverage'} and physical_props(actions) and not re.search(r'\b(?:hands?|body|person|people|character)\b',actions,re.I)))) else ', '.join(visible) or UNKNOWN,
            'props':'None' if graphic or audio_only else ', '.join(physical_props(actions)) or 'None specified',
            'shot_type':shot_type,'shot_location':'Graphic' if graphic else 'Audio / Post' if audio_only else ctx.get('location',scene['location']),
            'day_night':'Not applicable' if graphic or audio_only else scene['day_night'],
            'interior_exterior':'Not applicable' if graphic or audio_only else scene['interior_exterior'],
            'sound_cues':[e['text'] if not e['speaker'] else e['speaker']+': '+e['text'] for e in group if e['type'] in ('Music Cue','Voice Over') or e.get('heard_only')],
            'dialogue_present':'Dialogue' in types,
            'sfx_cues':[e['text'] for e in group if e['type']=='SFX'],
            'vfx_cues':[e['text'] for e in group if e['type']=='VFX'],
            'speed_treatment':speed,'visual_treatment':treatment,
            'facts':{'location':scene['location'],'time':scene['day_night'],'temporal_context':scene.get('temporal_context','Present')},
            'assumed_fields':[] if graphic or audio_only else ['Framing/movement suggestions unless explicitly directed by the script']}
        # Panel-local locations do not overwrite the scene's shared context.
        for e in group:
            if e['type']=='Split Screen Panel':
                m=SCENE.match(e['text'].split(':',1)[-1].strip())
                if m:
                    p=re.split(r'\s+[-–—]\s+',m[2]);row['shot_location']=p[0];row['interior_exterior']=m[1].replace('.','').upper();row['day_night']=p[1] if len(p)>1 else scene['day_night']
        if re.search(r'\bno talent (?:in frame|on camera)\b',actions,re.I):row['cast']='None'
        elif row['cast']==UNKNOWN and 'Coverage' in types and re.search(r'\bpeople\b',actions,re.I):row['cast']='Background people; casting / permissions to confirm'
        shots.append(normalize(row))
    return shots

def generate_plan(scene,characters=None,offset=0,previous=None):
    if not isinstance(scene,dict) or not isinstance(scene.get('elements'),list) or not scene['elements']:
        raise UserError('No screenplay scene was supplied.')
    if sum(len(e.get('text','')) for e in scene['elements'])>18000:raise UserError('This scene is too long. Split it into smaller sequences.')
    draft=draft_plan(scene,offset)
    if provider_name()=='demo':return assign_production_numbers(draft,offset,previous)
    result=complete(PLAN_PROMPT,{'scene':scene,'character_memory':characters or [],'draft':draft,'preceding_shots':previous or []})
    rows=result.get('shots')
    if not isinstance(rows,list) or not rows or len(rows)>100:raise UserError('The AI did not return a usable shot plan. Regenerate this scene.',502)
    by_beat={b['number']:b for b in scene['beats']};by_draft={r['beat']:r for r in draft}
    available={e['id']:e for e in scene['elements']};required={n for n,e in available.items() if e['type'] not in METADATA}
    covered=set();previous_beat=0;counts={};output=[]
    for proposed in rows:
        if not isinstance(proposed,dict):raise UserError('The AI returned an invalid shot. Please regenerate.',502)
        if any(not isinstance(v,str) or len(v)>15000 for k,v in proposed.items() if k in PLAN_FIELDS):raise UserError('The AI returned invalid shot field types. Please regenerate.',502)
        ids=proposed.get('source_ids',[])
        if not isinstance(ids,list) or not ids or any(type(n)!=int or n not in available for n in ids):raise UserError('The AI could not link its shots to your script. Regenerate this scene.',502)
        beat_number=text(proposed.get('beat'))
        matches=[b for b in scene['beats'] if set(ids).issubset(b['source_ids'])]
        if not beat_number and len(matches)==1:beat_number=matches[0]['number']
        beat_ids=proposed.get('beat_ids') or [beat_number]
        if not isinstance(beat_ids,list) or any(not isinstance(n,str) or n not in by_beat for n in beat_ids):raise UserError('The AI returned unknown beat identities.',502)
        selected_beats=[by_beat[n] for n in beat_ids]
        positions=[list(by_beat).index(n) for n in beat_ids]
        if beat_number!=beat_ids[0] or positions!=list(range(positions[0],positions[0]+len(positions))):raise UserError('Grouped coverage must use adjacent beats in screenplay order.',502)
        if beat_number not in by_beat or not set(ids).issubset({n for b in selected_beats for n in b['source_ids']}) or not safe_group(selected_beats):raise UserError('The AI grouped incompatible production setups. Regenerate this scene.',502)
        beat=by_beat[beat_number];ordinal=int(beat_number.split('.')[-1])
        if ordinal<previous_beat:raise UserError('The AI changed the script order. Regenerate this scene.',502)
        previous_beat=int(beat_ids[-1].split('.')[-1]);covered.update(ids)
        row={**by_draft[beat_number],**{k:text(v) for k,v in proposed.items() if k in PLAN_FIELDS or k in ('shot_type','shot_purpose')}}
        for k in ['scene_name','beat','source_script_block']:row[k]=by_draft[beat_number][k]
        counts[beat_number]=counts.get(beat_number,0)+1;row['number']=f'{beat_number}.{counts[beat_number]}'
        row['id']='';row['source_ids']=sorted(set(ids))
        selected=[available[n] for n in ids];start=min(e['source_start'] for e in selected);end=max(e['source_end'] for e in selected)
        row['source_spans']=[];blocks=[]
        for b in selected_beats:
            chosen=[e for e in selected if e['id'] in b['source_ids']]
            if not chosen:continue
            a=min(e['source_start'] for e in chosen);z=max(e['source_end'] for e in chosen);origin=b['source_spans'][0]['start']
            blocks.append(b['source_script_block'][a-origin:z-origin]);row['source_spans'].append({'start':a,'end':z})
        row['source_script_block']=''.join(blocks);row['source_order']=start;row['beat_ids']=beat_ids
        for key,types in [('sound_cues',{'Music Cue','Voice Over'}),('sfx_cues',{'SFX'}),('vfx_cues',{'VFX'})]:
            row[key]=[(e['speaker']+': ' if e['speaker'] else '')+e['text'] for e in selected if e['type'] in types or (key=='sound_cues' and e.get('heard_only'))]
        row['script']='\n'.join((e['speaker']+': ' if e['speaker'] else '')+e['text'] for e in sorted(selected,key=lambda e:e['id']) if e['type'] not in METADATA|AUDIO|{'Transition','Parenthetical'}) or row['source_script_block']
        if any(e['type'] in GRAPHICS for e in selected):
            if any(e['type'] not in GRAPHICS|METADATA|AUDIO|{'Transition'} for e in selected):raise UserError('The AI combined a graphic with live action. Regenerate this scene.',502)
            row.update(shot_type='Title Card / Graphic',shot_size='Full Screen Graphic',shot_angle='Not applicable',camera_movement='Static',cast='None',props='None')
        heard={e['speaker'] for e in selected if e.get('heard_only') and e['speaker']}
        present=set(scene.get('context',{}).get('cast_present',[]))
        if any(n.lower() in row.get('cast','').lower() and n not in present for n in heard):raise UserError('The AI placed an off-screen voice in the visible cast. Regenerate this scene.',502)
        if not row['shot_description'] or not row['shot_size']:raise UserError('The AI returned incomplete shot descriptions. Regenerate this scene.',502)
        row['shot_type_purpose']='';output.append(normalize(row))
    if not required.issubset(covered):raise UserError('The AI omitted part of your screenplay. Regenerate this scene; your original script is safe.',502)
    return assign_production_numbers(output,offset,previous)

BREAKDOWN_PROMPT='''You are a production designer, DOP and first AD working together. Return {"shots":[...]}.
Each approved shot is one production row. Retain its id. Never add/remove units or change approved scene/beat/shot,
source text, framing, cast, action or location. Generate coherent requirements, not independent columns.
Preserve reliable imported fields. Use the shared scene context and source evidence. Do not turn figurative dialogue
into physical props. Include extras, costume/hair/makeup, sound/music/VO, practical SFX vs VFX/post, continuity,
reference and explicit uncertainties. Heard-only voices are not cast in frame. Graphics have no physical cast/props.
Write practical concise requirements. Use assumptions for genuinely unresolved facts and proposed equipment/FPS.
Keep optional Clip No. blank. Do not fill every field with Confirmation Required. Notes combine SFX, music, VO,
VFX, transitions and continuity. Leave VISUALS blank unless the user supplied a manual visual reference.
For continuous shots use the same wardrobe, lighting and set facts unless the source explicitly changes them.
Return all requested production fields as strings. Avoid inventing exact frame rates, costumes or locations.'''

def base_breakdown(row):
    row=normalize(row);graphic=is_graphic(row);audio=row['shot_type']=='Audio / Post';physical=not graphic and not audio
    ctx=row.get('scene_context',{});assumptions=[]
    costumes=ctx.get('costumes',{})
    visible=[n.strip() for n in row['cast'].split(',') if n.strip() not in ('None',UNKNOWN)]
    wardrobe='; '.join(f'{n}: {costumes.get(n,UNKNOWN)}' for n in visible) or UNKNOWN
    lighting='; '.join(ctx.get('lighting',[])) or UNKNOWN
    art='; '.join(ctx.get('art_setup',[])) or UNKNOWN
    speed=row.get('speed_treatment','Normal speed')
    for field,value in [('wardrobe / hair / makeup',wardrobe),('lighting',lighting),('art / set dressing',art),('exact location',row['shot_location'])]:
        if UNKNOWN in value:assumptions.append(field)
    result={**row,'location_setup':'Digital composition' if graphic else 'Audio recording / post' if audio else f'{row["shot_location"]}; camera position and access: {UNKNOWN}',
        'fps':'Not applicable' if not physical else speed+'; capture / playback FPS: '+UNKNOWN,
        'extras':'None' if not physical else '; '.join(ctx.get('extras',[])) or 'None specified; confirm background needs',
        'costumes':'None' if not physical else wardrobe+'; hair / makeup: '+ctx.get('hair_makeup',UNKNOWN),
        'lighting':'Not applicable' if not physical else lighting,
        'design_elements':row['script'] if graphic else row.get('visual_treatment','Normal') if 'Split' in row['shot_type'] else 'None specified',
        'art_setup':'Digital title design' if graphic else 'Not applicable' if audio else art,
        'sfx':'; '.join(row.get('sfx_cues',[])) or 'None specified',
        'sound':'; '.join(row.get('sound_cues',[])) or ('Dialogue / sync sound' if row.get('dialogue_present') else 'None specified'),
        'vfx':'; '.join(row.get('vfx_cues',[])) or ('Split-screen compositing; panel timing and eyelines must match' if 'Split' in row['shot_type'] else 'Graphic composition' if graphic else 'None specified'),
        'production_requirements':'Graphic/title-card creation' if graphic else 'Voice / sound recording and post-production' if audio else 'Confirm location access, cast availability, camera setup and sync sound',
        'continuity':f'Temporal context: {row.get("temporal_context","Present")}. '+('Maintain graphic style across cards.' if graphic else 'Match established location, wardrobe, hair/makeup, lighting and set dressing. '+(f'Props and positions: {row["props"]}. ' if row['props'] not in ('None','None specified') else '')+(f'Scene cast presence: {", ".join(ctx.get("cast_present",[]))}.' if ctx.get('cast_present') else '')),
        'reference':'Source spans '+', '.join(f'{s["start"]}–{s["end"]}' for s in row.get('source_spans',[])) if row.get('source_spans') else row.get('source_provenance',UNKNOWN),
        'assumptions':('FACT: Graphic content from source. CONFIRMATION REQUIRED: graphic style and duration.' if graphic else
            'FACT: See Source Script Block and scene context. ASSUMPTION: Proposed framing and execution. CONFIRMATION REQUIRED: '+', '.join(assumptions+(['capture/playback FPS'] if physical else ['voice casting and recording treatment'])))}
    source=row['source_script_block'];unresolved=[];requirements=[]
    equipment=next((name for pattern,name in [(r'\bmagic arm\b','Magic Arm'),(r'\bphone rig\b','Phone rig'),(r'\bgimbal\b','Gimbal'),(r'\bslider\b','Slider'),(r'\bdolly\b','Dolly'),(r'\btripod\b','Tripod')] if re.search(pattern,source,re.I)),None)
    if not physical:equipment='N/A'
    elif not equipment:
        equipment={'Static':'Tripod','Locked Off':'Tripod','Pan':'Tripod','Tilt':'Tripod','Handheld':'Handheld'}.get(row['camera_movement'],UNKNOWN)
        unresolved.append('Proposed '+equipment+' support to confirm' if equipment!=UNKNOWN else 'Camera support to confirm')
    fps=re.search(r'\b(\d{2,3})\s*FPS\b',source,re.I)
    result['fps']='N/A' if not physical else fps[1]+' FPS' if fps else 'Slow motion — capture FPS to confirm with DoP' if 'Slow motion' in speed else '24 FPS'
    if physical and not fps:unresolved.append('Slow-motion capture FPS to confirm with DoP' if 'Slow motion' in speed else '24 FPS proposed; confirm project frame rate')
    if not physical:result.update(shot_location='N/A',day_night='N/A',interior_exterior='N/A',lighting='N/A',costumes='N/A')
    else:
        if lighting==UNKNOWN:
            result['lighting']='Soft daylight / bounce (proposed)' if row['day_night'].upper() in ('DAY','DAWN','DUSK') else 'Night practicals + controlled fill (proposed)' if row['day_night'].upper()=='NIGHT' else UNKNOWN
            unresolved.append('Lighting setup to confirm with DoP')
        if row['cast']=='None':result['costumes']='N/A'
        else:
            result['costumes']=wardrobe if wardrobe!=UNKNOWN else 'Maintain established scene look'
            if wardrobe==UNKNOWN or UNKNOWN in wardrobe:unresolved.append('Wardrobe / hair / makeup to confirm')
        if row['shot_location']==UNKNOWN:unresolved.append('Exact location TBD')
    if graphic:requirements.append('Create title / graphic; confirm style and duration')
    if audio:requirements.append('Voice / sound recording')
    if re.search(r'\b(?:bike|road|traffic|street)\b',source,re.I):requirements.append('Road / traffic access and permissions to confirm')
    if re.search(r'\b(?:screen|interface|UI|ChatGPT)\b',source,re.I):requirements.append('Prepare interface / screen capture; confirm display legibility')
    if re.search(r'\b(?:food|cooking|tea|saucepan|stove)\b',row['script'],re.I):requirements.append('Food preparation and reset continuity')
    if 'match cut' in source.lower():requirements.append('Match framing / action across takes for match cut')
    if row.get('sfx_cues'):requirements.append('Confirm practical effect / sound execution: '+'; '.join(row['sfx_cues']))
    if row.get('vfx_cues'):requirements.append('Confirm VFX capture plates and tracking requirements')
    if ctx.get('extras'):requirements.append('Background: '+'; '.join(ctx['extras']))
    transitions=[line.strip() for line in source.splitlines() if re.search(r'\b(?:match cut|motion blur|long take|post push|two options|whip pan|transition)\b',line,re.I)]
    notes=[*transitions]
    for key,label in [('sfx','SFX'),('sound','Sound / VO'),('vfx','Post')]:
        if result[key] not in ('None specified','Graphic composition'):notes.append(label+': '+result[key])
    if row.get('temporal_context','Present')!='Present':notes.append('Time: '+row['temporal_context'])
    if visible and physical:notes.append('Continuity: maintain scene wardrobe and prop positions')
    if row.get('group_reason'):notes.append(row['group_reason'])
    if row.get('assumptions'):unresolved.append(row['assumptions'])
    visual=('Eye / '+', '.join(visible)) if visible and re.search(r'\beye\b',row['shot_description'],re.I) else ' / '.join(physical_props(row['shot_description'])) or ('Stage title graphic' if graphic else ', '.join(visible)) or row['shot_type']
    result.update(equipment=equipment,visuals=row.get('visuals',''),notes='\n'.join(dict.fromkeys(notes)),clip_no=row.get('clip_no',''),
                  production_requirements='; '.join(requirements),assumptions='; '.join(dict.fromkeys(unresolved)),
                  art_graphics=row['script'] if graphic else '; '.join(ctx.get('art_setup',[])) or ('Screen / interface content' if re.search(r'\b(?:screen|interface|UI|ChatGPT)\b',source,re.I) else ''))
    # Reviewed plan values win over inferred production defaults.
    for key in ('visuals','equipment','fps','lighting','notes','costumes','art_graphics','production_requirements','assumptions','clip_no'):
        if row.get(key):result[key]=row[key]
    # All reliable imported production values override proposed defaults, except immutable identity.
    for key,value in row.get('existing',{}).items():
        if key in (set(PRODUCTION)|set(INTERNAL)) and key not in IDENTITY_FIELDS and text(value):result[key]=text(value)
    # Older saved projects carry special instructions in separate internal fields.
    if row.get('existing') and not row['existing'].get('notes'):
        legacy=production_view({**result,'schema_version':2,'notes':''})['notes']
        result['notes']='\n'.join(dict.fromkeys(filter(None,[result['notes'],legacy])))
    result.update(production_view(result))
    return normalize(result)

def generate_breakdown(plan,scene,prior=None):
    targets=[r for r in plan if r['scene']==str(scene)]
    if not targets:raise UserError('That scene is not in the approved shot plan.')
    if len(targets)>100:raise UserError('This scene exceeds 100 shots. Split it into smaller scenes.')
    base=[base_breakdown(r) for r in targets]
    if provider_name()=='demo':return base
    result=complete(BREAKDOWN_PROMPT,{'plan':targets,'adjacent_scene_context':prior or [],'fields':PRODUCTION,'conservative_draft':base})
    ai=result.get('shots',[])
    if not isinstance(ai,list) or any(not isinstance(r,dict) for r in ai):raise UserError('The AI returned an invalid breakdown. Please retry.',502)
    if any(not isinstance(r.get('id'),str) or any(not isinstance(v,str) or len(v)>15000 for k,v in r.items() if k in PRODUCTION) for r in ai):raise UserError('The AI returned invalid production field types. Please retry.',502)
    by_id={r.get('id'):r for r in ai}
    if len(ai)!=len(targets) or set(by_id)!=set(r['id'] for r in targets):raise UserError('The AI changed the approved shot list. Please retry.',502)
    for r in base:
        for k in PRODUCTION:
            if k in ('equipment','fps','lighting','notes','costumes','art_graphics','production_requirements','assumptions') and not next(p for p in targets if p['id']==r['id']).get(k) and k not in r.get('existing',{}) and text(by_id[r['id']].get(k)):
                # Established scene facts win over a model's per-row embellishment.
                if k in ('lighting','costumes','art_setup','extras') and r[k] not in (UNKNOWN,'None specified; confirm background needs') and UNKNOWN not in r[k]:continue
                r[k]=text(by_id[r['id']][k])
        if is_graphic(r):r.update(cast='None',props='None',costumes='N/A',extras='None',lighting='N/A',fps='N/A',equipment='N/A',shot_location='N/A')
    return [normalize(r) for r in base]
