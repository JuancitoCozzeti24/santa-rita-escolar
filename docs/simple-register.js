// Acceso ultra simple: nombre + apellido + PIN. Crea o entra automáticamente.
(function(){
  const oldRenderAuth=renderAuth;
  renderAuth=function(){
    const el=document.querySelector('#authSide');
    if(profile){oldRenderAuth();return;}
    el.innerHTML=`<div class="eyebrow">CUENTA ONLINE</div>
      <h2>Entra a jugar</h2>
      <p>Escribe solo tu nombre, un apellido y tu PIN de 6 dígitos.</p>
      <label class="field">Nombre</label>
      <input id="firstName" class="input" autocomplete="given-name" maxlength="24" placeholder="Ej.: Matías">
      <label class="field">Apellido</label>
      <input id="surname" class="input" autocomplete="family-name" maxlength="24" placeholder="Ej.: Aliaga">
      <label class="field">PIN de 6 dígitos</label>
      <input id="simplePin" class="input" inputmode="numeric" maxlength="6" type="password" placeholder="••••••">
      <button id="simpleBtn" class="primary full" style="margin-top:16px">ENTRAR A JUGAR ⚔</button>
      <div class="msg" id="authMsg"></div>`;

    document.querySelector('#simpleBtn').onclick=async()=>{
      const first=document.querySelector('#firstName').value.trim();
      const surname=document.querySelector('#surname').value.trim();
      const pin=document.querySelector('#simplePin').value.trim();
      const msg=document.querySelector('#authMsg');
      const piece=/^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-]{2,24}$/;
      if(!piece.test(first)){msg.textContent='Escribe solo tu nombre de pila.';return;}
      if(!piece.test(surname)){msg.textContent='Escribe solo un apellido.';return;}
      if(!/^\d{6}$/.test(pin)){msg.textContent='El PIN debe tener exactamente 6 dígitos.';return;}
      msg.textContent='Preparando tu cuenta…';
      try{
        const d=await api('/simple-access',{method:'POST',body:{first_name:first,surname,pin}});
        token=d.token;profile=d.profile;localStorage.setItem(KEY+'_token',token);msg.textContent='';home();
        setTimeout(()=>{try{showIntro(false);}catch(e){}},180);
      }catch(e){
        msg.textContent=e.code==='invalid_pin'?'El PIN debe tener 6 dígitos.':e.code==='invalid_name'?'Revisa tu nombre y apellido.':'No pude entrar. Intenta nuevamente.';
      }
    };
  };
  setTimeout(()=>{try{if(!profile&&screen==='home')home();}catch(e){}},0);
})();
