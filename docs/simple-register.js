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
      <label class="field" id="nameLabel">Nombre real o usuario</label>
      <input id="simpleName" class="input" autocomplete="name" placeholder="Ej.: Matías Aliaga">
      <label class="field">PIN de 6 dígitos</label>
      <input id="simplePin" class="input" inputmode="numeric" maxlength="6" type="password" placeholder="••••••">
      <button id="simpleBtn" class="primary full" style="margin-top:16px">INICIAR SESIÓN</button>
      <div class="msg" id="authMsg"></div>`;
    let mode='login';
    const loginTab=document.querySelector('#loginTab'), newTab=document.querySelector('#newTab'), btn=document.querySelector('#simpleBtn'), label=document.querySelector('#nameLabel'), input=document.querySelector('#simpleName');
    function setMode(m){
      mode=m; loginTab.classList.toggle('active',m==='login'); newTab.classList.toggle('active',m==='new');
      btn.textContent=m==='login'?'INICIAR SESIÓN':'CREAR CUENTA Y JUGAR';
      label.textContent=m==='login'?'Nombre real o usuario':'Nombre real y apellido';
      input.placeholder=m==='login'?'Ej.: Matías Aliaga o matias':'Ej.: Matías Aliaga';
    }
    loginTab.onclick=()=>setMode('login'); newTab.onclick=()=>setMode('new');
    btn.onclick=async()=>{
      const raw=document.querySelector('#simpleName').value.trim().replace(/\s+/g,' '), pin=document.querySelector('#simplePin').value.trim(), msg=document.querySelector('#authMsg');
      if(mode==='new' && !validRealName(raw)){msg.textContent='Escribe tu nombre real y al menos un apellido.';return;}
      if(mode==='login' && raw.length<4){msg.textContent='Escribe tu nombre o usuario.';return;}
      if(!/^\d{6}$/.test(pin)){msg.textContent='El PIN debe tener exactamente 6 dígitos.';return;}
      const username=raw.includes(' ')?slugName(raw):String(raw).toLowerCase().trim();
      if(username.length<4){msg.textContent='No pude reconocer el nombre o usuario.';return;}
      msg.textContent=mode==='new'?'Creando tu cuenta…':'Entrando…';
      try{
        if(mode==='new'){
          const d=await api('/register',{method:'POST',body:{username,pin,section:'PUBLIC',display_name:raw,avatar:'⚡'}});
          token=d.token; profile=d.profile; localStorage.setItem(KEY+'_token',token); msg.textContent=''; home(); return;
        }
        const d=await api('/login',{method:'POST',body:{username,pin}});
        token=d.token; profile=d.profile; localStorage.setItem(KEY+'_token',token); msg.textContent=''; home();
      }catch(e){
        if(e.code==='username_taken') msg.textContent='Ya existe una cuenta con ese nombre. Usa “Ya tengo cuenta” e ingresa tu PIN.';
        else if(e.code==='invalid_credentials') msg.textContent='Nombre/usuario o PIN incorrecto.';
        else msg.textContent='No se pudo completar el registro. Intenta nuevamente.';
      }
    };
  };
  setTimeout(()=>{try{if(!profile && screen==='home')home();}catch(e){}},0);
})();
