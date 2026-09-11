// Registro simple: nombre real + PIN. Sin listas, secciones ni selección posterior.
(function(){
  function slugName(name){
    return String(name||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim()
      .replace(/[^a-z0-9]+/g,'.').replace(/^\.+|\.+$/g,'').slice(0,20);
  }
  function validRealName(name){
    const s=String(name||'').trim().replace(/\s+/g,' ');
    return s.length>=4 && s.includes(' ');
  }
  const oldRenderAuth=renderAuth;
  renderAuth=function(){
    const el=document.querySelector('#authSide');
    if(profile){ oldRenderAuth(); return; }
    el.innerHTML=`<div class="eyebrow">CUENTA ONLINE</div>
      <h2>Entra a la batalla</h2>
      <p>Solo necesitas tu nombre real y un PIN de 6 dígitos.</p>
      <div class="auth-tabs"><button id="loginTab" class="active">YA TENGO CUENTA</button><button id="newTab">NUEVO JUGADOR</button></div>
      <label class="field">Nombre real y apellido</label>
      <input id="simpleName" class="input" autocomplete="name" placeholder="Ej.: Matías Aliaga">
      <label class="field">PIN de 6 dígitos</label>
      <input id="simplePin" class="input" inputmode="numeric" maxlength="6" type="password" placeholder="••••••">
      <button id="simpleBtn" class="primary full" style="margin-top:16px">INICIAR SESIÓN</button>
      <div class="msg" id="authMsg"></div>`;
    let mode='login';
    const loginTab=document.querySelector('#loginTab'), newTab=document.querySelector('#newTab'), btn=document.querySelector('#simpleBtn');
    function setMode(m){mode=m;loginTab.classList.toggle('active',m==='login');newTab.classList.toggle('active',m==='new');btn.textContent=m==='login'?'INICIAR SESIÓN':'CREAR CUENTA Y JUGAR';}
    loginTab.onclick=()=>setMode('login'); newTab.onclick=()=>setMode('new');
    btn.onclick=async()=>{
      const name=document.querySelector('#simpleName').value.trim().replace(/\s+/g,' '), pin=document.querySelector('#simplePin').value.trim(), msg=document.querySelector('#authMsg');
      if(!validRealName(name)){msg.textContent='Escribe tu nombre real y al menos un apellido.';return;}
      if(!/^\d{6}$/.test(pin)){msg.textContent='El PIN debe tener exactamente 6 dígitos.';return;}
      const username=slugName(name);
      if(username.length<4){msg.textContent='No pude crear tu usuario. Escribe tu nombre y apellido completos.';return;}
      msg.textContent=mode==='new'?'Creando tu cuenta…':'Entrando…';
      try{
        if(mode==='new'){
          const d=await api('/register',{method:'POST',body:{username,pin,section:'PUBLIC',display_name:name,avatar:'⚡'}});
          token=d.token; profile=d.profile; localStorage.setItem(KEY+'_token',token); msg.textContent=''; home(); return;
        }
        const d=await api('/login',{method:'POST',body:{username,pin}});
        token=d.token; profile=d.profile; localStorage.setItem(KEY+'_token',token); msg.textContent=''; home();
      }catch(e){
        if(e.code==='username_taken') msg.textContent='Ya existe una cuenta con ese nombre. Usa “Ya tengo cuenta” e ingresa tu PIN.';
        else if(e.code==='invalid_credentials') msg.textContent='Nombre o PIN incorrecto. Si tu cuenta antigua usaba otro usuario, escríbelo sin espacios en el campo de nombre.';
        else msg.textContent='No se pudo completar el registro. Intenta nuevamente.';
      }
    };
  };
  // Re-renderiza la portada para aplicar el formulario simple incluso en la primera carga.
  setTimeout(()=>{try{if(!profile && screen==='home')home();}catch(e){}},0);
})();
