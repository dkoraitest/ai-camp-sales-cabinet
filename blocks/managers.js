/* Блок «Менеджеры». Подключается сборщиком: scripts/build_cabinet.py */
/* -------------------------- МЕНЕДЖЕРЫ -------------------------- */
function renderManagers(){
  const coach = DataSource.coaching();
  let html = '<div class="cards">';
  DataSource.managers().forEach(m => {
    const mine = DataSource.contacts().filter(c => c.manager_id === m.id);
    const scored = mine.map(c => scoreOf(c.id)).filter(Boolean);
    const avg = scored.length ? scored.reduce((a,s)=>a+s.total,0)/scored.length : null;
    const fb = coach ? (coach.managers||[]).find(x => x.id === m.id) : null;

    html += '<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline">'+
      '<strong>'+esc(m.name)+'</strong>'+
      (avg!==null ? '<span class="pill '+grade(avg,10)+'">'+avg.toFixed(1)+'</span>' : '<span class="pill">—</span>')+'</div>'+
      '<div class="muted small" style="margin-top:2px">'+esc(m.role)+'</div>'+
      '<div class="kpi-note">'+mine.length+' контактов · '+
        mine.filter(c=>c.kind==='call').length+' звонков, '+mine.filter(c=>c.kind==='chat').length+' переписок</div>';

    if(fb && (fb.skills||[]).length){
      html += '<div style="margin-top:14px"><div class="kpi-label">Карта навыков</div>';
      fb.skills.forEach(s => {
        html += '<div class="skill"><div class="lbl"><span>'+esc(s.name)+'</span>'+
          '<span class="muted">'+s.value+'/'+(s.max||10)+'</span></div>'+
          '<div class="bar '+grade(s.value,s.max||10)+'"><i style="width:'+Math.round(s.value/(s.max||10)*100)+'%"></i></div></div>';
      });
      html += '</div>';
    }
    if(fb){
      html += '<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--line)">'+
        '<div class="kpi-label">Обратная связь</div><p class="small" style="margin:6px 0 0">'+esc(fb.summary)+'</p>';
      if(fb.focus) html += '<p class="muted small" style="margin:8px 0 0"><b>Фокус недели:</b> '+esc(fb.focus)+'</p>';
      if(fb.quote) html += '<p class="small" style="margin:10px 0 0;padding:10px 12px;background:var(--panel-2);'+
        'border-radius:10px;border-left:2px solid var(--accent)">'+esc(fb.quote)+'</p>';
      html += '</div>';

      if(fb.drill){
        html += '<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--line)">'+
          '<div class="kpi-label">Тренировка · '+esc(fb.drill.skill_name||'')+'</div>'+
          '<p class="small" style="margin:6px 0 0"><b>'+esc(fb.drill.title)+'</b></p>'+
          '<p class="muted small" style="margin:6px 0 0">'+esc(fb.drill.task)+'</p>'+
          (fb.drill.expected ? '<p class="muted small" style="margin:6px 0 0"><b>Что проверяем:</b> '+esc(fb.drill.expected)+'</p>' : '')+
          '</div>';
      }
      (fb.telegram_messages||[]).forEach(t => {
        html += '<div class="tg"><div class="meta">Telegram '+esc(fb.telegram||'')+
          ' · '+esc(t.trigger||'')+'</div>'+esc(t.text)+'</div>';
      });
    }
    html += '</div>';
  });
  html += '</div>';

  if(!coach) html += '<h2>Карта навыков и обратная связь</h2>'+
    emptyBlock('Тренер ещё не подключён',
      'Кабинет оценивает разговоры, но пока не объясняет менеджеру, что делать иначе, и не тренирует слабые места.','шага 2');
  return html;
}
registerTab({ id: 'managers', label: 'Менеджеры', render: renderManagers });
