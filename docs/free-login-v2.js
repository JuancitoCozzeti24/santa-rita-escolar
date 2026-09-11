// Entrada totalmente libre: cualquier nombre, sin PIN, lista, grado ni sección.
(function(){
  const oldRenderAuth=renderAuth;
  renderAuth=function(){
    const el=document.querySelector('#authSide');
    if(profile){ oldRenderAuth(); return; }
    el.innerHTML=`<div class="eyebrow">ENTRADA LIBRE</div>
      <h2>Escribe tu nombre</h2>
      <p>Puede ser cualquier nombre. Ese será el nombre que aparecerá en el ranking global.</p>
      <label class="field">Nombre</label>
      <input id="freeName" class="input" autocomplete="off" placeholder="Ej.: Matías">
      <button id="freeEnter" class="primary full" style="margin-top:16px">JUGAR AHORA ⚔</button>
      <div class="msg" id="freeMsg"></div>`;
    const input=document.querySelector('#freeName'), btn=document.querySelector('#freeEnter'), msg=document.querySelector('#freeMsg');
    async function enter(){
      const name=input.value.trim().replace(/\s+/g,' ');
      if(!name){msg.textContent='Escribe un nombre.';return;}
      btn.disabled=true; msg.textContent='Entrando…';
      try{
        const d=await api('/school-login',{method:'POST',body:{full_name:name}});
        token=d.token; profile=d.profile; localStorage.setItem(KEY+'_token',token); msg.textContent='';
        home();
      }catch(e){btn.disabled=false;msg.textContent='No se pudo entrar. Intenta otra vez.';}
    }
    btn.onclick=enter;
    input.addEventListener('keydown',e=>{if(e.key==='Enter')enter();});
    setTimeout(()=>input.focus(),50);
  };
  setTimeout(()=>{try{if(!profile&&screen==='home')home();}catch(e){}},0);
})();