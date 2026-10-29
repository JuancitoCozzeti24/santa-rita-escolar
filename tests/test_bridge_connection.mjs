import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../browser_extension/connection.js',import.meta.url),'utf8');
function setup(fetcher, saved={}) {
  const storage={...saved}; const calls=[];
  const ctx={window:{},URL,Headers,AbortController,setTimeout,clearTimeout,TypeError,Error,
    chrome:{runtime:{getManifest:()=>({version:'0.8.7'})},storage:{local:{get:async()=>({...storage}),set:async x=>Object.assign(storage,x)}}},
    fetch:async(url,options)=>{calls.push({url,options});return fetcher(url,options);}};
  vm.runInNewContext(source,ctx);
  return {api:ctx.window.SieRoomConnection,storage,calls};
}
const json=(obj,status=200)=>new Response(JSON.stringify(obj),{status,headers:{'Content-Type':'application/json'}});
test('migration preserves the exact secret and teacher configuration',async()=>{
 const {api,storage}=setup(()=>{}, {endpoint:'https://santa-rita-escolar-tcpb.onrender.com/',secret:'synthetic',teacherEmail:'teacher@example.edu'});
 await api.config();assert.equal(storage.endpoint,'https://sieroom-src.onrender.com');assert.equal(storage.secret,'synthetic');assert.equal(storage.teacherEmail,'teacher@example.edu');
 assert.throws(()=>api.normalizeEndpoint('https://untrusted.example'));
 assert.throws(()=>api.normalizeEndpoint('https://sieroom-src.onrender.com/private'));
});
test('save/check requires authenticated status, exact version and triple contract',async()=>{
 const {api,calls}=setup(url=>json(url.endsWith('/status')?{ok:true,bridge:'SieRoom Classroom Bridge',version:'0.8.7',queue:{work_remaining:0}}:{ok:true,compatible:true,triple_contract:true}));
 await api.check(api.DEFAULT_ENDPOINT,'synthetic');assert.equal(calls.length,2);
 assert.equal(calls[0].options.headers.get('X-SieRoom-Bridge-Secret'),'synthetic');
 assert.equal(calls[0].options.headers.get('X-SieRoom-Bridge-Build'),api.BUILD);
 assert.equal(calls[0].options.redirect,'error');
});
test('HTTP and network errors fail clearly without leaking secrets',async()=>{
 for (const [status,message] of [[401,/401/],[404,/404/],[500,/500/]]) {
  const {api}=setup(()=>json({error:'failed'},status));await assert.rejects(api.check(api.DEFAULT_ENDPOINT,'synthetic'),message);
 }
 const {api}=setup(()=>{throw new TypeError('Failed to fetch');});
 await assert.rejects(api.check(api.DEFAULT_ENDPOINT,'synthetic'),/No se pudo conectar/);
});
test('HTTP 200 HTML or malformed success and mismatched versions are rejected',async()=>{
 for (const response of [()=>new Response('<html>login</html>'),()=>json({ok:true}),()=>json({ok:true,bridge:'SieRoom Classroom Bridge',version:'0',queue:{}})]) {
  const {api}=setup(response);await assert.rejects(api.check(api.DEFAULT_ENDPOINT,'synthetic'));
 }
});
test('207 partial completion retains its existing behavior',async()=>{
 const {api}=setup(()=>json({ok:false,partial:true},207));
 assert.equal((await api.request(api.DEFAULT_ENDPOINT,'/bridge/v1/jobs/test/complete')).status,207);
});
test('only institutional permissions; transport and root mirrors packaged',()=>{
 const root=new URL('../',import.meta.url);const manifest=JSON.parse(readFileSync(new URL('browser_extension/manifest.json',root)));
 assert.deepEqual(manifest.host_permissions,['https://classroom.google.com/*','https://sieroom-src.onrender.com/*']);
 assert.equal(manifest.version,'0.8.7');
 for(const name of ['connection.js','manifest.json','popup.js','bridge.js','delete_bridge.js','popup.html','bridge.html'])assert.equal(readFileSync(new URL(name,root),'utf8'),readFileSync(new URL('browser_extension/'+name,root),'utf8'));
 for(const name of ['popup.html','bridge.html'])assert.ok(readFileSync(new URL('browser_extension/'+name,root),'utf8').indexOf('connection.js')>=0);
});

test('actual Guardar y probar handler preserves settings and verifies teacher without processing jobs',async()=>{
 const elements=Object.fromEntries(['endpoint','teacherEmail','secret','msg','save','start','reset'].map(id=>[id,{value:'',textContent:'',addEventListener(type,fn){this[type]=fn;}}]));
 const saved={endpoint:'https://santa-rita-escolar-tcpb.onrender.com',teacherEmail:'jbringas@santaritadecasia.edu.pe',secret:'synthetic-only'};
 const calls=[];
 const ctx={window:{},URL,Headers,AbortController,setTimeout,clearTimeout,TypeError,Error,
  document:{getElementById:id=>elements[id]},
  chrome:{runtime:{getManifest:()=>({version:'0.8.7'})},storage:{local:{get:async()=>({...saved}),set:async x=>Object.assign(saved,x)}},
   tabs:{query:async()=>[{id:1,active:true}],sendMessage:async(id,msg)=>{assert.equal(msg.expectedEmail,saved.teacherEmail);return {ok:true};}}},
  fetch:async(url,options)=>{calls.push({url,options});return json(url.endsWith('/status')?{ok:true,bridge:'SieRoom Classroom Bridge',version:'0.8.7',queue:{work_remaining:0}}:{ok:true,compatible:true,triple_contract:true});}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 ctx.SieRoomConnection=ctx.window.SieRoomConnection;
 vm.runInContext(readFileSync(new URL('../browser_extension/popup.js',import.meta.url),'utf8'),ctx);
 await new Promise(setImmediate);
 await elements.save.click();
 assert.match(elements.msg.textContent,/Conexión correcta/);
 assert.match(elements.msg.textContent,/Cuenta de Classroom confirmada/);
 assert.equal(saved.endpoint,'https://sieroom-src.onrender.com');assert.equal(saved.secret,'synthetic-only');
 assert.deepEqual(calls.map(x=>new URL(x.url).pathname),['/bridge/v1/status','/bridge/v1/compatibility']);
 assert.ok(calls.every(x=>!x.options.method || x.options.method==='GET'));
});
