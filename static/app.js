'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const API_BASE=(globalThis.SCRIPT2SET_API_BASE_URL||'').replace(/\/$/,'');
let authToken='';try{authToken=globalThis.sessionStorage?.getItem('s2s-token')||'';}catch{}
const fresh=()=>({version:3,continuity:{characters:{},locations:{},scenes:{}},metadata:{},title:'Untitled production',script:'',plan:[],breakdown:[],approval:'',planHash:'',breakdownHash:'',stale:false,analysis:null,images:{},visualContext:'Hand-drawn cinematic storyboard, charcoal pencil on warm white paper, restrained grayscale, 16:9 composition. Confirm character appearance, wardrobe and set design before final generation.'});
let state=fresh(), config={}, view='script', selected=new Set(), editing=null, working=false, db, saveChain=Promise.resolve();
const labels={scene:'Scene number',scene_name:'Scene / Sequence name',beat:'Beat number',number:'Shot number / range',source_script_block:'Source Script Block (original, read-only)',script:'Script / Relevant dialogue',shot_description:'Visual action / Shot description',shot_purpose:'Shot purpose',shot_size:'Shot size',shot_angle:'Shot angle',camera_movement:'Camera movement',cast:'Characters visible',props:'Props visible',shot_type:'Shot type',shot_location:'Shot location',day_night:'Day / Night',interior_exterior:'Interior / Exterior',visuals:'Visual identifier',equipment:'Equipment',fps:'FPS',lighting:'Lighting',notes:'Notes',costumes:'Costume / Hair / Makeup',art_graphics:'Art / Set / Graphics',production_requirements:'Production requirements',assumptions:'Assumptions / Confirmation Required'};
const planKeys=Object.keys(labels);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const uid=()=>crypto.randomUUID();
function showError(e){$('#error').textContent=e.message||String(e);$('#error').hidden=false;$('#error').scrollIntoView({block:'nearest',behavior:'smooth'});}
function notice(text){$('#notice').textContent=text;$('#notice').hidden=!text;}
function payload(){return {plan:state.plan,breakdown:state.breakdown,approval:state.approval,breakdown_hash:state.breakdownHash,title:state.title,metadata:state.metadata,source_script:state.analysis?state.script:''};}
function ready(){return !!state.breakdown.length&&!state.stale&&state.breakdown.length===state.plan.length;}
async function api(path,data,raw=false){
  const form=data instanceof FormData;
  const response=await fetch(API_BASE+path,{method:data===undefined?'GET':'POST',headers:{'X-Script2Set':'1',...(authToken?{'Authorization':'Bearer '+authToken}:{}),...(!form&&data!==undefined?{'Content-Type':'application/json'}:{})},body:data===undefined?undefined:form?data:JSON.stringify(data)});
  if(!response.ok){if(response.status===401)$('#login-dialog').showModal();let error;try{error=(await response.json()).error;}catch{error='The server could not complete this request. Check your connection and try again.';}throw new Error(error);}
  return raw?response:response.json();
}
async function run(label,fn){
  if(working)return;
  working=true;$('#busy-text').textContent=label;$('#busy').hidden=false;$('#error').hidden=true;
  $$('button').forEach(b=>{b.dataset.wasDisabled=String(b.disabled);b.disabled=true;});
  try{await fn();await save();}catch(e){showError(e);}finally{working=false;$('#busy').hidden=true;$$('button').forEach(b=>{b.disabled=b.dataset.wasDisabled==='true';delete b.dataset.wasDisabled;});render();}
}
function openDb(){return new Promise((resolve,reject)=>{const req=indexedDB.open('script2set',1);req.onupgradeneeded=()=>req.result.createObjectStore('projects');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});}
async function save(){
  const snapshot=structuredClone(state);
  saveChain=saveChain.catch(()=>{}).then(()=>new Promise((resolve,reject)=>{
    if(!db){$('#save-status').textContent='Use Save project to keep a copy';resolve();return;}
    const tx=db.transaction('projects','readwrite');tx.objectStore('projects').put(snapshot,'current');
    tx.oncomplete=()=>{$('#save-status').textContent='Saved on this device';resolve();};
    tx.onerror=()=>{$('#save-status').textContent='Save failed — download a project copy';reject(new Error('Device storage is full or unavailable. Use Save project to download your work.'));};
  }));return saveChain;
}
function staleImages(){for(const img of Object.values(state.images)){img.approved=false;img.stale=true;img.status='outdated';}}
function staleImage(id){const image=state.images[id];if(image){image.approved=false;image.stale=true;image.status='outdated';}}
function changedPlan(){state.stale=!!state.breakdown.length;state.approval='';state.planHash='';staleImages();save().catch(showError);}
function switchView(name){view=name;selected.clear();$$('.view').forEach(el=>el.hidden=el.id!=='view-'+name);$$('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.view===name));$$('.workflow-bar button').forEach(el=>el.classList.toggle('current',el.dataset.view===name));render();}
function countText(rows){return rows.length?`${rows.length} shot rows · ${rows.filter(r=>r.coverage_label||/[-–—]/.test(r.number)).length} coverage groups · ${new Set(rows.map(r=>r.scene)).size} scenes`:'0 shots available';}
function render(){
  if(config.metadata_fields&&!$('#metadata-fields').children.length){$('#metadata-fields').innerHTML=Object.entries(config.metadata_fields).map(([k,l])=>`<label>${esc(l)}<input data-metadata="${k}" aria-label="${esc(l)}" maxlength="500"></label>`).join('');}
  $$('[data-metadata]').forEach(el=>{if(document.activeElement!==el)el.value=state.metadata?.[el.dataset.metadata]||'';});
  $('#project-title').value=state.title;$('#project-crumb').textContent=state.title;
  $('#plan-count').textContent=state.plan.length;$('#shot-status').textContent=countText(state.plan);$('#breakdown-status').textContent=countText(state.breakdown);
  $('#plan-empty').hidden=!!state.plan.length;$('#breakdown-empty').hidden=!!state.breakdown.length;
  $('#stale-banner').hidden=!state.stale;$('#approve-plan').disabled=!state.plan.length||working;
  $('#approve-plan').title=state.plan.length?'Approve this exact version and generate production requirements':'Generate or add a shot first';
  $('#duplicate-shots').disabled=!selected.size||working;$('#delete-shots').disabled=!selected.size||working;
  $('#renumber').disabled=!state.plan.length||working;
  for(const id of ['regenerate-row','regenerate-scene'])$( '#'+id).disabled=!ready()||working||(id==='regenerate-row'&&!selected.size);
  for(const button of $$('[data-export],#ppt-settings,#story-ppt,#print-export')){button.disabled=!ready()||working;button.title=ready()?'Export the latest edited breakdown':'Approve the current shot plan and generate its complete breakdown first';}
  if(view==='plan')renderPlan();
  if(view==='breakdown')renderBreakdown();
  if(view==='storyboard')renderStoryboard();
  $('#analysis-details').hidden=!state.analysis;
  $('#analysis-content').innerHTML=state.analysis?state.analysis.scenes.map(s=>`<p><strong>Scene ${esc(s.number)} · ${esc(s.name||s.heading)}</strong><br>${esc(s.boundary_reason||'Scene heading')}<br>${(s.beats||[]).map(b=>`Beat ${esc(b.number)}: ${esc(b.name)} — ${esc(b.reason)}`).join('<br>')}</p>`).join(''):'';
  const scenes=[...new Set(state.plan.map(r=>r.scene))], old=$('#scene-select').value;
  $('#scene-select').innerHTML=scenes.map(s=>`<option value="${esc(s)}">Scene ${esc(s)}</option>`).join('');if(scenes.includes(old))$('#scene-select').value=old;
}
function selectCell(r){return `<td class="tiny"><input type="checkbox" data-select="${esc(r.id)}" aria-label="Select shot ${esc(r.number)}" ${selected.has(r.id)?'checked':''}></td>`;}
function renderPlan(){
  $('#plan-table').innerHTML=state.plan.length?`<table><thead><tr><th></th><th>Shot</th><th>Source script / Dialogue</th><th>Visual action</th><th>Framing</th><th>Cast / Props</th><th></th></tr></thead><tbody>${state.plan.map(r=>`<tr>${selectCell(r)}<td><span class="shot-badge">${esc(r.number)}</span>Scene ${esc(r.scene)} · Beat ${esc(r.beat)}<br><span class="shot-tag">${esc(r.shot_type)}</span></td><td class="text-cell"><details><summary>Original source · Beat ${esc(r.beat)}</summary><p>${esc(r.source_script_block)}</p><small>${esc(r.source_provenance)}</small></details>${esc(r.script)}</td><td class="text-cell">${esc(r.shot_description)}<br><small class="muted">${esc(r.shot_purpose)}</small></td><td>${esc(r.shot_size)}<br>${esc(r.shot_angle)}<br>${esc(r.camera_movement)}</td><td>${esc(r.cast)}<br><small class="muted">${esc(r.props)}</small></td><td><button data-edit="${esc(r.id)}">Edit shot</button></td></tr>`).join('')}</tbody></table>`:'';
}
function renderBreakdown(){
  $('#breakdown-table').innerHTML=state.breakdown.length?`<table><thead><tr><th></th><th>Shot / Edit</th>${Object.values(config.columns||{}).map(l=>`<th>${esc(l)}</th>`).join('')}</tr></thead><tbody>${state.breakdown.map((r,i)=>`<tr class="${i===0||state.breakdown[i-1].scene!==r.scene?'scene-start':''}">${selectCell(r)}<td><span class="shot-badge">${esc(r.number)}</span><small>Scene ${esc(r.scene)} · ${esc(r.scene_name)}</small><button data-edit="${esc(r.id)}">Edit breakdown</button></td>${Object.keys(config.columns||{}).map(k=>`<td class="text-cell">${esc(r[k]||'')}</td>`).join('')}</tr>`).join('')}</tbody></table>`:'';
}
function renderStoryboard(){
  if(!ready()){$('#storyboard-content').innerHTML='<div class="empty"><h2>Your frames start with an approved plan.</h2><p>Generate a current production breakdown to begin storyboarding.</p><button data-view="plan" class="primary">Review shot plan →</button></div>';return;}
  $('#storyboard-content').innerHTML=`<div class="context-card"><strong>Visual continuity</strong><p>Define recurring identities and sets once. Scene entries can specify wardrobe or time changes. Save these notes before generating frames. Changes mark existing frames outdated.</p><label for="visual-context">Overall style</label><textarea id="visual-context">${esc(state.visualContext)}</textarea><button id="save-context">Save visual context</button><button id="edit-continuity">Characters, locations & scenes</button><p>${config.image_enabled?'Image provider configured. Generate and approve a reference frame first; related shots can use up to three approved reference images.':'Image generation is not configured. You can upload and approve images; no generated frames will be simulated.'}</p></div><div class="story-grid">${state.breakdown.map(r=>{const image=state.images[r.id];return `<article class="story-card"><div class="story-frame">${image?.data?`<img src="${esc(image.data)}" alt="Storyboard for shot ${esc(r.number)}">`:`<strong>${esc(r.number)}</strong><span>${esc(r.shot_size)}</span><span>STORYBOARD IMAGE PENDING</span>`}</div><div class="story-body"><h3>SHOT ${esc(r.number)} <span class="${image?.approved?'approved-tag':'pending-tag'}">${image?.stale?'Outdated — replace or regenerate':image?.approved?'✓ Approved':image?.data?'Review frame':'Awaiting frame'}</span></h3>${r.coverage_label?'<p>Representative frame for this coverage block.</p>':''}<p>${esc(r.shot_description)}</p>${image?.error?`<p role="alert">${esc(image.error)}</p>`:''}<div class="story-actions"><button data-image-generate="${esc(r.id)}" ${!config.image_enabled?'disabled title="Configure an image provider first"':''}>${image?.error?'Retry':image?.data?'Regenerate':'Generate'} frame</button><button data-image-upload="${esc(r.id)}">${image?.data?'Replace':'Upload'} image</button>${image?.data?`<button data-image-view="${esc(r.id)}">View</button><button data-image-approve="${esc(r.id)}" ${image.stale?'disabled':''}>${image.approved?'Unapprove':'Approve'} frame</button>`:''}</div></div></article>`;}).join('')}</div>`;
}
function imagePayload(id){return {...payload(),shot_id:id,visual_context:state.visualContext,continuity:state.continuity,images:exportImages()};}
async function generateFrame(id){return run('Generating storyboard frame — this may take a few minutes…',async()=>{
  const previous=state.images[id];
  try{const result=await api('/api/storyboard/generate',imagePayload(id));state.images[id]=result.image;notice('Frame generated. Review identity, framing and continuity before approval.');}
  catch(e){state.images[id]={...previous,status:'error',error:e.message};await save();throw e;}
});}
async function uploadFrame(id,data){return run('Saving replacement frame…',async()=>{state.images[id]=(await api('/api/storyboard/upload',{...imagePayload(id),image:data})).image;notice('Uploaded frame saved. Review it before approving.');});}
async function approveFrame(id){return run('Updating image approval…',async()=>{const image=state.images[id];state.images[id]=(await api('/api/storyboard/approve',{...imagePayload(id),asset_id:image.asset_id,approved:!image.approved})).image;});}
async function editContinuity(){return run('Loading scene continuity…',async()=>{
  const result=await api('/api/storyboard/context',{...payload(),continuity:state.continuity});
  $('#continuity-fields').innerHTML=Object.entries(result.continuity).map(([kind,entries])=>`<fieldset><legend>${esc(kind)}</legend>${Object.entries(entries).map(([key,value])=>`<label>${esc(key)}<textarea data-continuity-kind="${kind}" data-continuity-key="${esc(key)}" maxlength="3000">${esc(value)}</textarea></label>`).join('')}</fieldset>`).join('');
  $('#continuity-dialog').showModal();
});}
$('#continuity-form').onsubmit=e=>{e.preventDefault();const next={characters:{},locations:{},scenes:{}};$$('[data-continuity-kind]').forEach(el=>next[el.dataset.continuityKind][el.dataset.continuityKey]=el.value);if(JSON.stringify(next)!==JSON.stringify(state.continuity)){state.continuity=next;staleImages();}$('#continuity-dialog').close();save().catch(showError);render();};
$('#storyboard-upload').onchange=async e=>{const file=e.target.files[0],id=e.target.dataset.shotId;if(!file)return;try{if(file.size>10_000_000)throw new Error('Use an image under 10 MB.');const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Cannot read this image.'));reader.readAsDataURL(file);});await uploadFrame(id,data);}catch(err){showError(err);}e.target.value='';};
$('#save-server').onclick=()=>run('Saving project on the backend…',async()=>{const project=structuredClone(state);for(const image of Object.values(project.images)){if(image.asset_id)delete image.data;}const result=await api('/api/projects',{project});state.serverId=result.id;notice('Project and storyboard frames saved on the server. Keep a downloaded project copy as a backup.');});
$('#open-server').onclick=()=>run('Loading saved projects…',async()=>{const result=await api('/api/projects');$('#server-projects').innerHTML=result.projects.map(p=>`<option value="${esc(p.id)}">${esc(p.title)} — ${esc(p.updated)}</option>`).join('');$('#restore-server').disabled=!result.projects.length;$('#server-dialog').showModal();});
$('#restore-server').onclick=async()=>{const id=$('#server-projects').value;if(!id||!await confirmAction('Restore saved project?','This replaces your current workspace. Save a copy first to keep current changes.'))return;return run('Restoring saved project…',async()=>{const result=await api('/api/projects/'+encodeURIComponent(id));state={...fresh(),...result.project};$('#script-input').value=state.script;$('#char-count').textContent=state.script.length.toLocaleString()+' characters';$('#server-dialog').close();switchView(state.breakdown.length?'breakdown':state.plan.length?'plan':'script');notice('Project restored from server storage.');});};
function confirmAction(title,description){return new Promise(resolve=>{const dialog=$('#confirm-dialog');$('#confirm-title').textContent=title;$('#confirm-text').textContent=description;dialog.showModal();const done=v=>{dialog.close();resolve(v);};$('#confirm-yes').onclick=()=>done(true);$('#confirm-no').onclick=()=>done(false);dialog.oncancel=()=>resolve(false);});}
function renumber(){let n=1;state.plan.forEach((r,i)=>{const m=String(r.number).match(/^(\d+)\s*[-–—]\s*(\d+)(.*)$/);const count=m?Number(m[2])-Number(m[1])+1:1;const label=m?m[3]:r.coverage_label?' '+r.coverage_label:'';r.number=count>1?`${n}–${n+count-1}${label}`:`${n}${label}`;r.production_order=i;r.representative_shot=String(n);n+=count;});}
function editShot(id){
  const rows=view==='breakdown'?state.breakdown:state.plan;
  const row=rows.find(r=>r.id===id);if(!row)return;
  editing={id,stage:view==='breakdown'?'breakdown':'plan'};
  $('#edit-title').textContent=`${editing.stage==='plan'?'Shot':'Breakdown'} ${row.number}`;
  const fields=editing.stage==='plan'?labels:config.columns;
  $('#edit-fields').innerHTML=Object.entries(fields).map(([k,label])=>{
    const long=['source_script_block','script','shot_description','shot_purpose','assumptions','lighting','production_requirements','continuity','sound','sfx','vfx'].includes(k);
    const readonly=k==='source_script_block'||(editing.stage==='breakdown'&&['scene','scene_name','beat'].includes(k));
    return `<label class="${long?'full':''}">${esc(label)}${long?`<textarea aria-label="${esc(label)}" name="${k}" maxlength="15000" ${readonly?'readonly':''}>${esc(row[k])}</textarea>`:`<input aria-label="${esc(label)}" name="${k}" value="${esc(row[k])}" maxlength="2000" ${readonly?'readonly':''}>`}</label>`;
  }).join('');$('#edit-dialog').showModal();
}
$('#edit-form').addEventListener('submit',event=>{event.preventDefault();const row=state[editing.stage].find(r=>r.id===editing.id),values=Object.fromEntries(new FormData(event.target));delete values.source_script_block;Object.assign(row,values);if(values.size_angle){[row.shot_size,row.shot_angle='']=values.size_angle.split(' / ');}if(values.day_int_ext){[row.day_night,row.interior_exterior='']=values.day_int_ext.split(' / ');}if(editing.stage==='plan'){row.size_angle='';row.day_int_ext='';}row.size_movement=[row.shot_size,row.camera_movement].filter(Boolean).join(' / ');if(editing.stage==='plan'){row.shot_type_purpose=[row.shot_type,row.shot_purpose].filter(Boolean).join(' / ');if(row.existing){for(const k in values)if(k in row.existing)row.existing[k]=values[k];delete row.existing.size_angle;delete row.existing.day_int_ext;delete row.existing.size_movement;}changedPlan();}else{staleImage(row.id);save().catch(showError);}$('#edit-dialog').close();render();});
$$('.close-dialog').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
document.addEventListener('click',event=>{
  if(!working){
    const generate=event.target.closest('[data-image-generate]');if(generate)generateFrame(generate.dataset.imageGenerate);
    const upload=event.target.closest('[data-image-upload]');if(upload){$('#storyboard-upload').dataset.shotId=upload.dataset.imageUpload;$('#storyboard-upload').click();}
    const approve=event.target.closest('[data-image-approve]');if(approve)approveFrame(approve.dataset.imageApprove);
    const frame=event.target.closest('[data-image-view]');if(frame){$('#full-frame').src=state.images[frame.dataset.imageView].data;$('#frame-dialog').showModal();}
    if(event.target.id==='save-context'){if(state.visualContext!==$('#visual-context').value){state.visualContext=$('#visual-context').value;staleImages();save().catch(showError);}render();}
    if(event.target.id==='edit-continuity')editContinuity();
  }

  const viewButton=event.target.closest('[data-view]');if(viewButton&&!working)switchView(viewButton.dataset.view);
  const edit=event.target.closest('[data-edit]');if(edit&&!working)editShot(edit.dataset.edit);
  const exportButton=event.target.closest('[data-export]');if(exportButton&&!working)downloadExport(exportButton.dataset.export);
});
document.addEventListener('input',event=>{if(event.target.matches('[data-metadata]')){state.metadata[event.target.dataset.metadata]=event.target.value;save().catch(showError);}});
document.addEventListener('change',event=>{if(event.target.matches('[data-select]')){const id=event.target.dataset.select;event.target.checked?selected.add(id):selected.delete(id);render();}});
$('#project-title').addEventListener('input',event=>{state.title=event.target.value;$('#project-crumb').textContent=state.title;save().catch(showError);});
$('#script-input').addEventListener('input',event=>{state.script=event.target.value;$('#char-count').textContent=state.script.length.toLocaleString()+' characters';save().catch(showError);});
$('#paste-tab').onclick=()=>{$('#paste-panel').hidden=false;$('#upload-panel').hidden=true;$('#paste-tab').classList.add('selected');$('#upload-tab').classList.remove('selected');$('#generate-plan').hidden=false;};
$('#upload-tab').onclick=()=>{$('#paste-panel').hidden=true;$('#upload-panel').hidden=false;$('#upload-tab').classList.add('selected');$('#paste-tab').classList.remove('selected');$('#generate-plan').hidden=true;};
$('#generate-plan').onclick=async()=>{
  if(state.plan.length&&!await confirmAction('Replace the current shot plan?','Your current plan, breakdown and storyboard frames will be replaced. Save a project copy first if you want to retain them.'))return;
  run('Reading your screenplay…',async()=>{
    const analysis=await api('/api/analyze',{script:state.script});let shots=[];
    for(const [i,scene] of analysis.chunks.entries()){
      $('#busy-text').textContent=`Planning sequence ${i+1} of ${analysis.chunks.length}…`;
      const result=await api('/api/plan',{scene,characters:analysis.characters,offset:shots.length,previous:shots.slice(-4)});
      shots.push(...result.shots);if(shots.length>300)throw new Error('This script produced more than 300 shots. Split it into smaller projects.');
    }
    state.plan=shots;state.analysis=analysis;state.breakdown=[];state.breakdownHash='';changedPlan();
    notice(config.provider==='demo'?'Offline preview: this draft uses conservative rules, not an AI model. Configure Ollama or cloud AI for cinematic interpretation.':'Shot plan generated. Review each shot before approving your production breakdown.');switchView('plan');
  });
};
$('#excel-input').onchange=event=>{const file=event.target.files[0];if(!file)return;(async()=>{
  if(state.plan.length&&!await confirmAction('Import a new shot sheet?','This replaces the current plan and breakdown. Save your current project first if needed.'))return;
  await run('Reading your workbook…',async()=>{const form=new FormData();form.append('file',file);const result=await api('/api/import',form);state.plan=result.shots;state.metadata={...state.metadata,...result.metadata};state.breakdown=[];state.analysis=null;changedPlan();notice(`Imported ${result.shots.length} shots from “${result.worksheet}”. Existing values are preserved. Review and approve to complete missing requirements. ${result.warnings.join(' ')}`);switchView('plan');});event.target.value='';
})();};
$('#add-shot').onclick=()=>{const scene=state.plan.at(-1)?.scene||'1';const row={id:uid(),scene,scene_name:state.plan.at(-1)?.scene_name||'New scene',beat:state.plan.at(-1)?.beat||`${scene}.1`,source_script_block:'Manual production unit — no original screenplay source attached',source_provenance:'Manual addition',number:`${scene}.${state.plan.filter(r=>r.scene===scene).length+1}`,script:'',shot_description:'New shot — describe what the camera sees',shot_purpose:'',shot_size:'Medium',shot_angle:'Eye level',camera_movement:'Static',cast:'Confirmation Required',props:'Confirmation Required',shot_type:'Live Action',shot_location:'Confirmation Required',day_night:'Confirmation Required',interior_exterior:'Confirmation Required'};state.plan.push(row);renumber();changedPlan();render();editShot(row.id);};
$('#duplicate-shots').onclick=()=>{state.plan=state.plan.flatMap(r=>selected.has(r.id)?[r,{...structuredClone(r),id:uid()}]:[r]);renumber();changedPlan();selected.clear();render();};
$('#delete-shots').onclick=async()=>{if(await confirmAction('Delete selected shots?',`${selected.size} selected shots will be removed. Any production breakdown will need to be regenerated.`)){state.plan=state.plan.filter(r=>!selected.has(r.id));renumber();changedPlan();selected.clear();render();}};
$('#renumber').onclick=()=>{renumber();changedPlan();render();notice('Shots renumbered in screenplay order.');};
$('#reapprove').onclick=()=>switchView('plan');
$('#approve-plan').onclick=async()=>{
  if(state.breakdown.length&&!await confirmAction('Regenerate the production breakdown?','This approves your current shot plan and replaces the existing breakdown, including manual production edits. Storyboard approvals will be reset.'))return;
  run('Approving your shot plan…',async()=>{
    const approval=await api('/api/approve',{plan:state.plan,reviewed:true});
    const scenes=[...new Set(state.plan.map(r=>r.scene))];let breakdown=[];
    for(const [i,scene] of scenes.entries()){
      $('#busy-text').textContent=`Building breakdown for scene ${scene} (${i+1}/${scenes.length})…`;
      const result=await api('/api/breakdown',{plan:state.plan,approval:approval.approval,scene,prior:breakdown.slice(-4)});breakdown.push(...result.shots);
    }
    state.approval=approval.approval;state.planHash=approval.plan_hash;state.breakdownHash=approval.plan_hash;state.breakdown=breakdown;state.stale=false;staleImages();
    notice('Production breakdown ready. Review requirements and confirmation notes before sending them to your crew.');switchView('breakdown');
  });
};
async function regenerate(selectedOnly){
  const ids=new Set(selected),scene=$('#scene-select').value;
  if(!await confirmAction('Regenerate production requirements?',selectedOnly?'Selected rows will be replaced. Other manual edits will be retained.':'This scene’s production rows will be replaced. Other scenes will be retained.'))return;
  run('Regenerating production requirements…',async()=>{
    const scenes=selectedOnly?[...new Set(state.plan.filter(r=>ids.has(r.id)).map(r=>r.scene))]:[scene];
    for(const s of scenes){const result=await api('/api/breakdown',{...payload(),scene:s,prior:state.breakdown.filter(r=>r.scene!==s).slice(-4)});for(const row of result.shots){if(!selectedOnly||ids.has(row.id)){state.breakdown[state.breakdown.findIndex(r=>r.id===row.id)]=row;staleImage(row.id);}}}
    notice('Production requirements regenerated. Review any assumptions before export.');
  });
}
$('#regenerate-row').onclick=()=>regenerate(true);$('#regenerate-scene').onclick=()=>regenerate(false);
function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.textContent='Download '+name;const box=$('#download-ready');if(box.dataset.url)URL.revokeObjectURL(box.dataset.url);box.dataset.url=url;box.replaceChildren(a);box.hidden=false;a.click();}
function exportImages(){return Object.fromEntries(Object.entries(state.images).filter(([,image])=>image.approved&&!image.stale).map(([id,image])=>[id,{asset_id:image.asset_id,approved:true}]));}
async function downloadExport(kind){return run(`Preparing ${kind.toUpperCase()} export…`,async()=>{
  if(kind==='xlsx'){
    const review=await api('/api/validate',payload());
    const describe=items=>items.map(v=>(v.shot?'Shot '+v.shot+': ':'')+v.message).join('\n\n');
    if(!review.ok)throw new Error('Resolve these accuracy checks before Excel export:\n\n'+describe(review.errors));
    if(review.warnings.length&&!await confirmAction('Review production assumptions',describe(review.warnings)+'\n\nContinue with these warnings? They are also recorded in Excel comments.'))return;
  }
  const response=await api('/api/export/'+kind,{...payload(),per_slide:Number($('#ppt-layout').value),images:['xlsx','pptx'].includes(kind)?exportImages():{},visual_context:state.visualContext,continuity:state.continuity},true);download(await response.blob(),'script2set-breakdown.'+kind);notice(`${kind.toUpperCase()} export ready with your latest edits. Use the download link if your browser did not save it automatically.`);if(kind==='pptx')$('#ppt-dialog').close();});}
$('#ppt-settings').onclick=$('#story-ppt').onclick=()=>$('#ppt-dialog').showModal();$('#download-ppt').onclick=()=>downloadExport('pptx');
$('#print-export').onclick=()=>run('Preparing print view…',async()=>{const result=await api('/api/print',payload());if(!db)throw new Error('Printing needs browser storage. Enable it for Script2Set, or export Excel.');const key='print-'+uid();await new Promise((resolve,reject)=>{const tx=db.transaction('projects','readwrite');tx.objectStore('projects').put({...result,title:state.title},key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});const link=$('#print-ready');link.href='/print#'+key;link.hidden=false;window.open(link.href,'_blank','noopener');notice('Print view opened. If your browser blocked the new tab, allow pop-ups for this app.');});
$('#save-project').onclick=()=>download(new Blob([JSON.stringify(state,null,2)],{type:'application/json'}),'script2set-project.json');
$('#open-project').onclick=()=>$('#project-input').click();
$('#project-input').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>30_000_000)throw new Error('Project file is too large (maximum 30 MB).');const parsed=JSON.parse(await file.text());if(![1,2,3].includes(parsed.version)||!Array.isArray(parsed.plan)||!Array.isArray(parsed.breakdown)||parsed.plan.length>300||parsed.breakdown.length>300)throw new Error('This is not a supported Script2Set project file.');if(!await confirmAction('Open this project?','Your current workspace will be replaced by the selected project.'))return;state=(await api('/api/migrate',{project:{...fresh(),...parsed}})).project;$('#script-input').value=state.script;$('#char-count').textContent=state.script.length.toLocaleString()+' characters';await save();switchView(state.breakdown.length?'breakdown':state.plan.length?'plan':'script');notice('Project opened. If its approval was signed by a different server, review and approve again before exporting.');}catch(e){showError(e);}event.target.value='';};
$('#new-project').onclick=async()=>{if(await confirmAction('Start a new production?','This clears the current workspace. Download a project copy first to keep your work.')){state=fresh();$('#script-input').value='';$('#char-count').textContent='0 characters';await save();notice('');switchView('script');}};
$('#load-sample').onclick=async()=>{if(state.script&&!await confirmAction('Load the sample script?','This replaces the script input. Your existing shot plan stays available until you generate a new one.'))return;try{const r=await fetch('/static/sample.txt');state.script=await r.text();if(state.title==='Untitled production')state.title='The stages of brief';$('#script-input').value=state.script;$('#char-count').textContent=state.script.length.toLocaleString()+' characters';await save();render();}catch(e){showError(e);}};
$('#login-form').onsubmit=async e=>{e.preventDefault();try{const login=await api('/api/login',{password:$('#password').value});authToken=login.token;try{globalThis.sessionStorage?.setItem('s2s-token',authToken);}catch{}$('#password').value='';$('#login-dialog').close();config=await api('/api/config');if(state.version<3){state=(await api('/api/migrate',{project:state})).project;await save();render();}}catch(error){$('#login-error').textContent=error.message;}};
$('#login-dialog').addEventListener('cancel',e=>e.preventDefault());
async function boot(){
  try{db=await openDb();const saved=await new Promise((resolve,reject)=>{const req=db.transaction('projects').objectStore('projects').get('current');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});if(saved)state={...fresh(),...saved};}catch{notice('Device storage is unavailable. Use Save project to keep your work.');}
  try{config=await api('/api/config');$('#provider-label').textContent=config.provider==='demo'?'Offline preview':config.provider==='ollama'?'Local AI · Ollama':'Cloud AI · '+config.provider;$('#mode-hint').textContent=config.provider==='demo'?'Offline preview · no AI connected':'Ready with '+config.provider;$('#footer-status').textContent=config.production?'PRIVATE CLOUD WORKSPACE':'LOCAL WORKSPACE';if(config.login_required)$('#login-dialog').showModal();else if(state.version<3){state=(await api('/api/migrate',{project:state})).project;await save();notice('Project upgraded to the production Shot List. Existing edits are preserved; review and approve again.');}}catch(e){showError(e);}
  $('#script-input').value=state.script;$('#char-count').textContent=state.script.length.toLocaleString()+' characters';switchView(state.breakdown.length?'breakdown':state.plan.length?'plan':'script');
}
boot();
