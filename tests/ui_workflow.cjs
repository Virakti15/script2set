// DOM-free integration, not a browser test. Executes the shipped handlers and real Flask routes.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),cp=require('child_process'),readline=require('readline'),path=require('path');
const root=path.resolve(__dirname,'..');
const child=cp.spawn(process.env.TEST_PYTHON||'python',[path.join(__dirname,'api_bridge.py')],{cwd:root,env:process.env,stdio:['pipe','pipe','inherit']});
const pending=new Map();let sequence=0;
readline.createInterface({input:child.stdout}).on('line',line=>{const data=JSON.parse(line);pending.get(data.id)?.(data);pending.delete(data.id);});
function request(url,options={}){return new Promise(resolve=>{const id=++sequence;pending.set(id,r=>resolve({ok:r.status<400,status:r.status,json:async()=>r.json,text:async()=>Buffer.from(r.data,'base64').toString(),blob:async()=>new Blob([Buffer.from(r.data,'base64')])}));child.stdin.write(JSON.stringify({id,path:url,method:options.method||'GET',data:options.body?JSON.parse(options.body):undefined})+'\n');});}
class Element{
  constructor(tag='div'){this.tagName=tag;this.value='';this.hidden=false;this.disabled=false;this.dataset={};this.children=[];this.listeners={};this.classList={toggle(){},add(){},remove(){}};this._html='';this.textContent='';}
  set innerHTML(v){this._html=v;}get innerHTML(){return this._html;}
  addEventListener(name,fn){this.listeners[name]=fn;}scrollIntoView(){}showModal(){this.open=true;}close(){this.open=false;}
  append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}click(){this.clicked=true;}remove(){}
  matches(){return false;}closest(){return this;}
}
const elements={};const template=fs.readFileSync(path.join(root,'templates/index.html'),'utf8');
for(const m of template.matchAll(/<([\w-]+)[^>]*\bid="([^"]+)"/g))elements['#'+m[2]]=new Element(m[1]);
const doc={listeners:{},querySelector:s=>elements[s]||null,querySelectorAll:s=>s==='button'?Object.values(elements).filter(x=>x.tagName==='button'):[],addEventListener(name,fn){this.listeners[name]=fn;},createElement:tag=>new Element(tag),activeElement:null};
elements['#ppt-layout'].value='1';
class FormDataStub{constructor(form){this.values=form.values;}[Symbol.iterator](){return Object.entries(this.values)[Symbol.iterator]();}}
const saved=new Map();
const fakeDb={transaction(){const tx={objectStore(){return {put(value,key){saved.set(key,structuredClone(value));queueMicrotask(()=>tx.oncomplete?.());},get(key){const req={};queueMicrotask(()=>{req.result=saved.get(key);req.onsuccess?.();});return req;}}}};return tx;}};
const context=vm.createContext({console,document:doc,crypto:require('crypto').webcrypto,structuredClone,FormData:FormDataStub,Blob,URL,setTimeout,clearTimeout,fetch:request,window:{open(url){context.openedPrint=url;}},indexedDB:{open(){const r={};queueMicrotask(()=>{r.result=fakeDb;r.onsuccess?.();});return r;}}});
const source=fs.readFileSync(path.join(root,'static/app.js'),'utf8');
vm.runInContext(source.replace(/boot\(\);\s*$/,'globalThis.test={getState:()=>state,setState:s=>state=s,getConfig:()=>config,setConfig:c=>config=c,setDb:d=>db=d,setView:v=>view=v,select:ids=>selected=new Set(ids),setEditing:e=>editing=e,payload,renumber,regenerate,ready,save,render,uploadFrame,approveFrame,exportImages,staleImages,staleImage};'),context);
const t=context.test;t.setDb(fakeDb);
async function settle(){for(let i=0;i<1000;i++){if(!vm.runInContext('working',context)){await new Promise(r=>setImmediate(r));return;}await new Promise(r=>setTimeout(r,5));}throw Error('Workflow did not settle');}
async function press(selector){assert(elements[selector],selector);await elements[selector].onclick();await settle();assert.equal(elements['#error'].hidden,true,elements['#error'].textContent);}
const checks=[];function check(name,fn){fn();checks.push(name);}
async function main(){
  t.setConfig(await (await request('/api/config')).json());
  const state=t.getState();state.title='Integration review';state.metadata={client:'Validation production',director:'Test director',aspect_ratio:'16:9'};
  state.script='INT. OFFICE - DAY\nMira: Ready?\nRavi: Yes.\nPROCESS: 13 ECU laptop workflow shots, static tripod, same screen setup.\nEXT. STREET - NIGHT\nMira walks to the gate.';
  await press('#generate-plan');
  check('Script → Shot Plan, individual + grouped range',()=>{assert.equal(state.plan.length,3);assert.equal(state.plan[1].number,'2–14 Process');assert.equal(state.plan[2].number,'15');});
  const original=state.plan[1].source_script_block;
  t.setEditing({stage:'plan',id:state.plan[1].id});
  state.plan[1].existing={size_angle:'Wide / High',day_int_ext:'NIGHT / EXT'};
  elements['#edit-form'].listeners.submit({preventDefault(){},target:{values:{number:'29-41 Process',shot_size:'ECU',shot_angle:'Top',day_night:'DAY',interior_exterior:'INT',source_script_block:'Tamper',equipment:'Magic Arm'}}});
  check('Plan edit, range edit and immutable source',()=>{assert.equal(state.plan[1].number,'29-41 Process');assert.equal(state.plan[1].source_script_block,original);assert.equal(state.plan[1].existing.size_angle,undefined);});
  t.select([state.plan[1].id]);await press('#duplicate-shots');
  check('Duplicate keeps range width, new ID and trace',()=>{assert.equal(state.plan.length,4);assert.notEqual(state.plan[1].id,state.plan[2].id);assert.equal(state.plan[2].number,'15–27 Process');assert.equal(state.plan[2].source_script_block,original);});
  vm.runInContext('confirmAction=async()=>true',context);
  t.select([state.plan[2].id]);await press('#delete-shots');
  check('Delete and stable production ordering',()=>{assert.equal(state.plan.length,3);assert.deepEqual(Array.from(state.plan,r=>r.production_order),[0,1,2]);});
  await press('#add-shot');
  check('Add manual shot has explicit source provenance',()=>{assert.equal(state.plan.length,4);assert.equal(state.plan[3].source_provenance,'Manual addition');});
  t.select([state.plan[3].id]);await press('#delete-shots');
  await press('#approve-plan');
  check('Approval → complete production breakdown',()=>{assert(t.ready());assert.equal(state.breakdown.length,3);assert.equal(state.breakdown[1].shot_angle,'Top');assert.equal(state.breakdown[1].equipment,'Magic Arm');});
  const validationPng='data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAkAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCOiiikYBRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAf//Z';
  const imageShot=state.breakdown[1].id;
  await t.uploadFrame(imageShot,validationPng);await settle();
  check('Storyboard upload handler saves unapproved replacement',()=>{assert(state.images[imageShot],elements['#error'].textContent);assert.equal(state.images[imageShot].source,'uploaded');assert.equal(state.images[imageShot].approved,false);assert(state.images[imageShot].data.startsWith('data:image/jpeg;base64,'));});
  await t.approveFrame(imageShot);await settle();
  check('Storyboard approval handler binds frame to grouped shot range',()=>{assert.equal(state.images[imageShot].approved,true);assert.equal(state.images[imageShot].number,'2–14 Process');assert.deepEqual(Object.keys(t.exportImages()),[imageShot]);});
  await press('#save-server');
  check('Backend save handler records durable project ID',()=>assert.match(state.serverId,/^[0-9a-f-]{36}$/));
  state.breakdown[0].notes='Keep unrelated manual edit';state.breakdown[1].notes='Replace this';
  t.select([state.plan[1].id]);await t.regenerate(true);await settle();
  check('Regenerate selected row preserves unrelated edits and marks image outdated',()=>{assert.equal(state.breakdown[0].notes,'Keep unrelated manual edit');assert.notEqual(state.breakdown[1].notes,'Replace this');assert.equal(state.images[imageShot].stale,true);assert.equal(state.images[imageShot].approved,false);assert.equal(Object.keys(t.exportImages()).length,0);});
  state.breakdown[2].notes='Keep other scene';elements['#scene-select'].value='1';await t.regenerate(false);await settle();
  check('Regenerate scene preserves other scene',()=>{assert.equal(state.breakdown[2].notes,'Keep other scene');assert.notEqual(state.breakdown[0].notes,'Keep unrelated manual edit');});
  t.setView('breakdown');t.setEditing({stage:'breakdown',id:state.breakdown[1].id});
  elements['#edit-form'].listeners.submit({preventDefault(){},target:{values:{number:'29-41 Process',size_angle:'ECU / Top',shot_description:'ECU of laptop workflow',notes:'Final edit',clip_no:'A001'}}});
  state.breakdown[2].number='42';
  for(const kind of ['xlsx','csv','pptx']){const exporting=vm.runInContext(`downloadExport('${kind}')`,context);if(kind==='xlsx'){for(let n=0;n<1000&&!elements['#confirm-dialog'].open&&!elements['#error'].textContent;n++)await new Promise(r=>setTimeout(r,5));if(elements['#confirm-dialog'].open)elements['#confirm-yes'].onclick();}await exporting;await settle();check(kind+' export handler receives actual file',()=>{assert(elements['#download-ready'].children[0].download.endsWith('.'+kind));assert.equal(elements['#error'].hidden,true,elements['#error'].textContent);});}
  await press('#print-export');
  const printed=saved.get(context.openedPrint.split('#')[1]);
  check('Print metadata/ranges/source mapping',()=>{assert.equal(printed.metadata.director,'Test director');assert.equal(printed.shots[1].number,'29-41 Process');assert.equal(printed.shots[1].source_script_block,original);assert.equal(Object.keys(printed.columns).length,19);});
  // Execute the actual print renderer with its shared storage payload.
  const printIds={};for(const id of ['print-button','title','print-status','print-content'])printIds[id]=new Element();
  const printContext=vm.createContext({document:{getElementById:id=>printIds[id],createElement:tag=>new Element(tag)},location:{hash:context.openedPrint.split('/print')[1]},indexedDB:context.indexedDB,window:{print(){}}});
  vm.runInContext(fs.readFileSync(path.join(root,'static/print.js'),'utf8'),printContext);await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));
  check('Print renderer builds metadata and all shot articles',()=>{assert.equal(printIds['print-content'].children.length,4);assert(printIds['print-content'].children[2].children[0].textContent.includes('29-41 Process'));assert.equal(printIds['print-content'].children[2].children[1].children.length,38);});
  await t.save();check('Saved project retains metadata and edits',()=>{assert.equal(saved.get('current').metadata.director,'Test director');assert.equal(saved.get('current').breakdown[1].clip_no,'A001');});
  t.setEditing({stage:'plan',id:state.plan[0].id});elements['#edit-form'].listeners.submit({preventDefault(){},target:{values:{shot_description:'Changed after approval'}}});
  const stale=await request('/api/export/csv',{method:'POST',body:JSON.stringify(t.payload())});
  check('Editing approved plan invalidates UI and server export',()=>{assert.equal(t.ready(),false);assert.equal(stale.status,409);});
  console.log(JSON.stringify({mode:'DOM-free actual UI handlers + real Flask routes; not browser E2E',passed:checks.length,checks},null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>child.stdin.end());
