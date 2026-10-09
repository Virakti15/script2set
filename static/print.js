'use strict';
document.getElementById('print-button').onclick=()=>window.print();
(async()=>{try{
  const key=location.hash.slice(1);if(!key.startsWith('print-'))throw new Error('Open the print view from your current production breakdown.');
  const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('script2set',1);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
  const data=await new Promise((resolve,reject)=>{const r=db.transaction('projects').objectStore('projects').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
  if(!data?.shots?.length)throw new Error('Open the print view from your current production breakdown.');
  document.getElementById('title').textContent=data.title||'Production breakdown';
  document.getElementById('print-status').textContent=`${data.shots.length} shots · Review all confirmation notes before production.`;
  const meta=document.createElement('dl');for(const [key,label] of Object.entries(data.metadata_fields||{})){if(data.metadata?.[key]){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=data.metadata[key];meta.append(dt,dd);}}document.getElementById('print-content').append(meta);
  for(const row of data.shots){
    const article=document.createElement('article'),h=document.createElement('h2'),dl=document.createElement('dl');h.textContent=`Scene ${row.scene} / Shot ${row.number}`;article.append(h,dl);
    for(const [field,label] of Object.entries(data.columns)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=row[field]||'';dl.append(dt,dd);}document.getElementById('print-content').append(article);
  }
}catch(e){document.getElementById('print-status').textContent=e.message;document.getElementById('print-button').disabled=true;}})();
