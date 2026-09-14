// Ingreso libre: solo escribe un nombre y entra a jugar.
(function(){
  const oldRenderAuth=renderAuth;
  renderAuth=function(){
    const el=document.querySelector('#authSide');
    if(profile){ oldRenderAuth(); return; }
    el.innerHTML=`<div class="eyebrow">ENTRADA RÁPIDA</div>
      <h2>¿Cómo te llamas?</h2>
      <p>Escribe el nombre que quieres que aparezca en el ranking.</p>
      <label class="field">Tu nombre</label>
      <input id="schoolFullName" class="input" autocomplete="name" placeholder="Ej.: Matías Aliaga">
      <button id="schoolEnter" class="primary full" style="margin-top:16px">ENTRAR A JUGAR ⚔</button>
      <div class="msg" id="schoolMsg"></div>`;
    const input=document.querySelector('#schoolFullName'), btn=document.querySelector('#schoolEnter'), msg=document.querySelector('#schoolMsg');
    async function enter(){
      const fullName=input.value.trim().replace(/\s+/g,' ');
      if(fullName.length<2){msg.textContent='Escribe tu nombre.';return;}
      btn.disabled=true; msg.textContent='Entrando…';
      try{
        const d=await api('/school-login',{method:'POST',body:{full_name:fullName}});
        token=d.token; profile=d.profile; localStorage.setItem(KEY+'_token',token); msg.textContent='';
        showIntro(false);
      }catch(e){
        btn.disabled=false;
        msg.textContent='No se pudo ingresar. Intenta nuevamente.';
      }
    }
    btn.onclick=enter;
    input.addEventListener('keydown',e=>{if(e.key==='Enter')enter();});
    setTimeout(()=>input.focus(),100);
  };
  setTimeout(()=>{try{if(!profile&&screen==='home')home();}catch(e){}},0);
})();
