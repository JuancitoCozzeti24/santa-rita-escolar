// Acceso escolar directo: solo nombre completo según la lista oficial.
(function(){
  const oldRenderAuth=renderAuth;
  renderAuth=function(){
    const el=document.querySelector('#authSide');
    if(profile){ oldRenderAuth(); return; }
    el.innerHTML=`<div class="eyebrow">INGRESO DIRECTO</div>
      <h2>Escribe tu nombre completo</h2>
      <p>Tal como aparece en la lista del colegio. No necesitas usuario, PIN ni elegir salón.</p>
      <label class="field">Nombre completo</label>
      <input id="schoolFullName" class="input" autocomplete="name" placeholder="Ej.: Matías Aliaga Pérez">
      <button id="schoolEnter" class="primary full" style="margin-top:16px">ENTRAR A JUGAR ⚔</button>
      <div class="msg" id="schoolMsg"></div>`;
    const input=document.querySelector('#schoolFullName'), btn=document.querySelector('#schoolEnter'), msg=document.querySelector('#schoolMsg');
    async function enter(){
      const fullName=input.value.trim().replace(/\s+/g,' ');
      if(fullName.length<5 || !fullName.includes(' ')){msg.textContent='Escribe tu nombre completo tal como figura en la lista del colegio.';return;}
      btn.disabled=true; msg.textContent='Buscando tu nombre…';
      try{
        const d=await api('/school-login',{method:'POST',body:{full_name:fullName}});
        token=d.token; profile=d.profile; localStorage.setItem(KEY+'_token',token); msg.textContent='';
        showIntro(false);
      }catch(e){
        btn.disabled=false;
        if(e.code==='student_not_found') msg.textContent='No encontré ese nombre. Escríbelo exactamente como aparece en la lista del colegio.';
        else if(e.code==='duplicate_name') msg.textContent='Hay dos estudiantes con el mismo nombre. Comunícate con el profesor.';
        else msg.textContent='No se pudo ingresar. Intenta nuevamente.';
      }
    }
    btn.onclick=enter;
    input.addEventListener('keydown',e=>{if(e.key==='Enter')enter();});
    setTimeout(()=>input.focus(),100);
  };
  setTimeout(()=>{try{if(!profile && screen==='home')home();}catch(e){}},0);
})();
