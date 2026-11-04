import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const probeSource = readFileSync(new URL("../browser_extension/classroom_account_probe.js", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("../browser_extension/popup.js", import.meta.url), "utf8");

function simulateProbe(accountLabel, origin = "https://classroom.google.com") {
  const element = {
    getBoundingClientRect: () => ({left:980, top:28, width:40, height:40}),
    getAttribute: k => k === "aria-label" ? accountLabel : null,
  };
  const context = {
    String, Set, location:{origin,href:origin + "/c/123"}, innerWidth:1200,
    getComputedStyle:()=>({display:"block",visibility:"visible"}),
    document: {
      readyState:"complete",
      querySelectorAll:()=>accountLabel?[element]:[],
    },
  };
  vm.runInNewContext(probeSource, context);
  return context.probeClassroomActiveAccount("teacher@school.edu");
}

test("verifies only the active top-right Google account", () => {
  const answer=simulateProbe("Cuenta de Google: Docente (teacher@school.edu)");
  assert.equal(answer.ok, true);
  assert.deepEqual(Array.from(answer.detectedEmails),["teacher@school.edu"]);
});

test("rejects a different account, no account, and an unrelated origin", () => {
  assert.equal(simulateProbe("Google Account: Student (student@school.edu)").ok,false);
  assert.equal(simulateProbe("").ok,null);
  assert.equal(simulateProbe("Google Account: Teacher (teacher@school.edu)","https://example.org").ok,null);
});

test("does not trust a secondary email or merely an authuser URL", () => {
  const account = simulateProbe("Cuenta de Google: personal@school.edu");
  assert.equal(account.ok,false);
  assert.equal(account.detectedEmails[0],"personal@school.edu");
});

async function popupWithTabs(tabs, inspectById) {
  const elements=Object.fromEntries(
    ["endpoint","teacherEmail","secret","msg","save","start","reset"]
      .map(id=>[id,{value:"",textContent:"",handlers:{},addEventListener(type,fn){this.handlers[type]=fn;}}])
  );
  elements.endpoint.value="https://sieroom-src.onrender.com";
  elements.teacherEmail.value="teacher@school.edu";
  elements.secret.value="test-secret";
  const calls=[];
  const storage={endpoint:elements.endpoint.value,teacherEmail:elements.teacherEmail.value,secret:elements.secret.value};
  const context={
    document:{getElementById:id=>elements[id]},
    SieRoomConnection:{
      normalizeEndpoint:x=>x,
      config:async()=>({...storage}),
      check:async()=>({version:"0.8.7"}),
    },
    chrome:{
      storage:{local:{get:async()=>({...storage}),set:async data=>Object.assign(storage,data)}},
      runtime:{getManifest:()=>({version:"0.8.7"}),getURL:x=>"chrome-extension://abcdef/"+x},
      tabs:{
        query:async()=>tabs,
        sendMessage:async()=>{throw Error("popup must not use content-script messages");},
        reload:async()=>{throw Error("popup must not reload Classroom");},
      },
      scripting:{executeScript:async ({target,args,func})=>{
        calls.push({target,args,hasProbe:typeof func==="function"});
        const result=inspectById[target.tabId];
        if(result instanceof Error)throw result;
        return [{result}];
      }},
    },
    setTimeout, Promise, Error, String, Number,
    window:{close(){}},
    fetch:async()=>{throw Error("not needed")},
  };
  vm.runInNewContext(probeSource,context);
  vm.runInNewContext(popupSource,context);
  await Promise.resolve();
  return {elements,calls};
}

test("popup verifies an already-open tab with no content script, no reload",async()=>{
  const env=await popupWithTabs([{id:42,active:true}],{42:{ok:true,detectedEmails:["teacher@school.edu"]}});
  await env.elements.save.handlers.click();
  assert.match(env.elements.msg.textContent,/verificada automáticamente/);
  assert.equal(env.calls.length,1);
});

test("popup searches another Classroom tab when first tab belongs to other account",async()=>{
  const env=await popupWithTabs(
    [{id:1,active:true},{id:2,active:false}],
    {1:{ok:false,detectedEmails:["student@school.edu"]},2:{ok:true,detectedEmails:["teacher@school.edu"]}}
  );
  await env.elements.save.handlers.click();
  assert.match(env.elements.msg.textContent,/verificada automáticamente/);
  assert.deepEqual(env.calls.map(x=>x.target.tabId),[1,2]);
});

test("popup fails closed if no active-account evidence is visible",async()=>{
  const env=await popupWithTabs(
    [{id:7,active:true}],{7:{ok:null,reason:"active_account_not_visible",detectedEmails:[]}}
  );
  await env.elements.save.handlers.click();
  assert.doesNotMatch(env.elements.msg.textContent,/verificada automáticamente/);
  assert.match(env.elements.msg.textContent,/No se ve el correo/);
  assert.doesNotMatch(env.elements.msg.textContent,/Recarga la pestaña/);
});

test("popup reports a genuine account mismatch without treating other accounts as success",async()=>{
  const env=await popupWithTabs([{id:5,active:true}],{5:{ok:false,detectedEmails:["other@school.edu"]}});
  await env.elements.save.handlers.click();
  assert.match(env.elements.msg.textContent,/Cuentas activas detectadas/);
  assert.doesNotMatch(env.elements.msg.textContent,/verificada automáticamente/);
});
