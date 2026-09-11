// Ranking live fix: fresh reads, silent polling, immediate refresh after score sync.
(function(){
  const originalApi = api;
  api = async function(path,opt={}){
    let nextPath = path;
    if ((opt.method||'GET').toUpperCase()==='GET' && path.includes('/leaderboard')) {
      nextPath += (path.includes('?')?'&':'?') + '_ts=' + Date.now();
    }
    const out = await originalApi(nextPath,opt);
    if (path==='/score' && out && out.ok) {
      if (profile && Number.isFinite(Number(out.personal_best))) {
        profile.best_score = Math.max(Number(profile.best_score||0), Number(out.personal_best||0));
      }
      setTimeout(()=>{
        try { if (document.querySelector('#rankList')) loadRank(rankSection||normalizeSec(profile?.section)||'2A', true); } catch(e) {}
        try { if (profile) loadMyRank(); } catch(e) {}
      },250);
    }
    return out;
  };

  loadRank = async function(s, silent=false){
    rankSection=s;
    document.querySelectorAll('[data-rank]').forEach(b=>b.classList.toggle('active',b.dataset.rank===s));
    const el=document.querySelector('#rankList');
    if(!el)return;
    if(!silent)el.innerHTML='<span class="muted">Cargando…</span>';
    try{
      const d=await api('/leaderboard?section='+encodeURIComponent(s)+'&limit=100');
      const rows=d.players||[];
      el.innerHTML=rows.length?rows.map((p,i)=>`<div class="rank-row ${i===0?'first':''}"><span class="place">${i<3?['🥇','🥈','🥉'][i]:p.rank}</span><span class="avatar" style="width:38px;height:38px;font-size:20px">${p.avatar||'⚡'}</span><span class="rank-name"><strong>${esc(p.display_name)}</strong><small>${sec(p.section)}</small></span><span class="pts">${p.best_score}</span></div>`).join(''):'<span class="muted">Aún no hay puntajes.</span>';
      el.dataset.updatedAt=d.updated_at||new Date().toISOString();
    }catch(e){
      if(!silent)el.innerHTML='<span class="muted">No se pudo cargar el ranking.</span>';
    }
  };

  loadMyRank = async function(){
    const s=normalizeSec(profile?.section);if(!s)return;
    try{
      const d=await api('/leaderboard?section='+encodeURIComponent(s)+'&limit=500');
      const r=(d.players||[]).find(x=>x.account_id===profile.account_id);
      const el=document.querySelector('#myRank');if(el)el.textContent=r?'#'+r.rank:'—';
      const me=(d.players||[]).find(x=>x.account_id===profile.account_id);
      if(me && profile){profile.best_score=Number(me.best_score||profile.best_score||0);const best=document.querySelector('.stat b');}
    }catch(e){}
  };

  setInterval(()=>{
    if(document.hidden || !profile) return;
    const list=document.querySelector('#rankList');
    if(list){
      try{loadRank(rankSection||normalizeSec(profile.section)||'2A',true);}catch(e){}
    }
    if(document.querySelector('#myRank')){
      try{loadMyRank();}catch(e){}
    }
  },4000);

  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden && profile){
      try{if(document.querySelector('#rankList'))loadRank(rankSection||normalizeSec(profile.section)||'2A',true);}catch(e){}
      try{if(document.querySelector('#myRank'))loadMyRank();}catch(e){}
    }
  });
})();
