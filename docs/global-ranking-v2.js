// Ranking global para el modo de entrada libre.
(function(){
  let seq=0;
  loadRank=async function(_s,silent=false){
    rankSection='GLOBAL';
    const id=++seq, el=document.querySelector('#rankList');
    if(!el)return;
    if(!silent)el.innerHTML='<span class="muted">Cargando ranking global…</span>';
    try{
      const d=await api('/leaderboard?limit=100&_ts='+Date.now());
      if(id!==seq)return;
      const rows=d.players||[];
      el.innerHTML=rows.length?rows.map((p,i)=>`<div class="rank-row ${i===0?'first':''}"><span class="place">${i<3?['🥇','🥈','🥉'][i]:i+1}</span><span class="avatar" style="width:38px;height:38px;font-size:20px">${p.avatar||'⚡'}</span><span class="rank-name"><strong>${esc(p.display_name||p.username)}</strong><small>Ranking global</small></span><span class="pts">${p.best_score||0}</span></div>`).join(''):'<span class="muted">Aún no hay puntajes.</span>';
    }catch(e){if(!silent)el.innerHTML='<span class="muted">No se pudo cargar el ranking global.</span>';}
  };
  loadMyRank=async function(){
    if(!profile)return;
    try{
      const d=await api('/leaderboard?limit=500&_ts='+Date.now());
      const r=(d.players||[]).find(x=>x.account_id===profile.account_id);
      const el=document.querySelector('#myRank'); if(el)el.textContent=r?'#'+r.rank:'—';
      if(r)profile.best_score=Number(r.best_score||profile.best_score||0);
    }catch(e){}
  };
  const oldRenderDash=renderDash;
  renderDash=function(){
    oldRenderDash();
    const tabs=document.querySelector('.rank-tabs'); if(tabs)tabs.innerHTML='<button class="active">GLOBAL</button>';
    const title=document.querySelector('.dashboard aside h2'); if(title)title.textContent='Ranking global';
    const sectionLabel=document.querySelector('.dashboard section .profile-head .muted'); if(sectionLabel)sectionLabel.textContent='Jugador libre';
    loadRank('GLOBAL');
  };
  setInterval(()=>{if(!document.hidden&&profile&&document.querySelector('#rankList'))loadRank('GLOBAL',true);},3000);
})();