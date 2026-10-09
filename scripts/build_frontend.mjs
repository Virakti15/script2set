import {mkdir,copyFile,cp,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const supplied=process.env.PUBLIC_API_BASE_URL;
if(!supplied)throw new Error('Set PUBLIC_API_BASE_URL to the hosted HTTPS backend origin.');
const url=new URL(supplied);
if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||!['','/'].includes(url.pathname)||['localhost','127.0.0.1','[::1]'].includes(url.hostname))throw new Error('PUBLIC_API_BASE_URL must be an HTTPS backend origin, without credentials, path, query or localhost.');
const api=url.origin;
const out=path.join(root,'frontend-dist');
await mkdir(out,{recursive:true});
await cp(path.join(root,'static'),path.join(out,'static'),{recursive:true});
await copyFile(path.join(root,'templates/index.html'),path.join(out,'index.html'));
await copyFile(path.join(root,'templates/print.html'),path.join(out,'print.html'));
await writeFile(path.join(out,'static/config.js'),`globalThis.SCRIPT2SET_API_BASE_URL = ${JSON.stringify(api)};\n`);
await writeFile(path.join(out,'_redirects'),'/print /print.html 200\n');
await writeFile(path.join(out,'_headers'),`/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: same-origin
  X-Frame-Options: DENY
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self' ${api}; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
/static/config.js
  Cache-Control: no-cache
`);
console.log('Static frontend built in frontend-dist; API origin: '+api);
