/* Блок «Менеджеры». Подключается сборщиком: scripts/build_cabinet.py */
/* -------------------------- МЕНЕДЖЕРЫ -------------------------- */
/* Карточка отвечает на вопрос руководителя: что с человеком и что ему уходит.
   Сам разбор и тексты для Telegram — в модалке: это письмо менеджеру,
   а не отчёт для чтения с экрана.                                          */
function renderManagers(){
  const coach = DataSource.coaching();
  const all = DataSource.managers();
  const detailed = coach ? new Set((coach.managers||[]).filter(x => x.summary).map(x => x.id)) : new Set();
  let html = '';

  // Большой отдел: сначала рейтинг таблицей, иначе двадцать карточек нечитаемы
  if(all.length > 8){
    const rows = all.map(m => { const s = mgrStats(m); return {m, n: s.mine.length, avg: s.avg} })
      .sort((a,b) => (b.avg ?? -1) - (a.avg ?? -1));
    html += '<h2>Рейтинг команды · '+all.length+' человек</h2><table><thead><tr>'+
      '<th>#</th><th>Менеджер</th><th>Контактов</th><th>Балл</th><th></th><th></th></tr></thead><tbody>';
    rows.forEach((r,i) => {
      html += '<tr><td class="muted">'+(i+1)+'</td><td>'+esc(r.m.name)+'</td>'+
        '<td class="muted">'+r.n+'</td>'+
        '<td>'+(r.avg!==null ? '<span class="pill '+grade(r.avg,10)+'">'+r.avg.toFixed(1)+'</span>' : '<span class="pill">—</span>')+'</td>'+
        '<td style="width:180px">'+(r.avg!==null ? '<div class="bar '+grade(r.avg,10)+'"><i style="width:'+Math.round(r.avg*10)+'%"></i></div>' : '')+'</td>'+
        '<td class="muted small">'+(detailed.has(r.m.id) ? 'разбор есть' : '')+'</td></tr>';
    });
    html += '</tbody></table>';
  }

  const shown = all.length > 8 && detailed.size ? all.filter(m => detailed.has(m.id)) : all;
  html += '<div class="rail-head"><h2>'+(all.length > 8 ? 'Разбор · '+shown.length+' из '+all.length : 'Команда')+'</h2>'+
    '<span id="rail-nav" style="display:none;align-items:center;gap:8px">'+
      '<button class="arrow" onclick="railScroll(-1)" title="Левее">&#8249;</button>'+
      '<button class="arrow" onclick="railScroll(1)" title="Правее">&#8250;</button>'+
      '<span class="muted small">листается вбок</span></span></div>';

  html += '<div class="rail" id="mgr-rail">';
  shown.forEach(m => {
    const {mine, avg} = mgrStats(m);
    const fb = coach ? (coach.managers||[]).find(x => x.id === m.id) : null;
    const weak = fb && (fb.skills||[]).length
      ? fb.skills.slice().sort((a,b) => a.value/(a.max||10) - b.value/(b.max||10))[0] : null;

    html += '<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline">'+
      '<strong>'+esc(m.name)+'</strong>'+
      (avg!==null ? '<span class="pill '+grade(avg,10)+'">'+avg.toFixed(1)+'</span>' : '<span class="pill">—</span>')+'</div>'+
      '<div class="muted small" style="margin-top:2px">'+esc(m.role)+
        (tgLinked(m.id) ? ' · <span class="pill good">Telegram</span>' : '')+'</div>'+
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
    if(weak) html += '<div class="weak"><div class="lbl">Слабое место</div>'+
      '<div class="val"><b>'+esc(weak.name)+'</b>'+
      '<span class="pill '+grade(weak.value,weak.max||10)+'">'+weak.value+'</span></div></div>';
    if(fb && fb.focus) html += '<p class="focus"><b>Фокус недели.</b> '+esc(shorten(fb.focus, 150))+'</p>';

    if(fb) html += '<div class="card-cta"><button class="act" onclick="openCoach(\''+m.id+'\')">'+
      (tgLinked(m.id) ? '' : '')+
      'Разбор и сообщения'+((fb.telegram_messages||[]).length ? ' · '+(fb.telegram_messages||[]).length : '')+' &rarr;</button></div>';
    html += '</div>';
  });
  html += '</div>';

  setTimeout(railNav, 0);
  if(!coach) html += '<h2>Карта навыков и обратная связь</h2>'+
    emptyBlock('Тренер ещё не подключён',
      'Кабинет оценивает разговоры, но пока не объясняет менеджеру, что делать иначе, и не тренирует слабые места.','шага 2');
  return html;
}
const shorten = (s, n) => s.length > n ? s.slice(0, n).replace(/[\s,;:—-]+\S*$/, '')+'…' : s;
function railScroll(dir){
  const r = $('#mgr-rail'); if(r) r.scrollBy({left: dir * 334, behavior: 'smooth'});
}
/* Стрелки нужны, только если лента не влезла: иначе кнопка, которая ничего
   не делает, выглядит как сломанная. */
function railNav(){
  const r = $('#mgr-rail'), nav = $('#rail-nav');
  if(r && nav) nav.style.display = r.scrollWidth > r.clientWidth + 4 ? 'inline-flex' : 'none';
}
window.addEventListener('resize', railNav);
function openCoach(id){
  const coach = DataSource.coaching(); if(!coach) return;
  const fb = (coach.managers||[]).find(x => x.id === id); if(!fb) return;
  const m = DataSource.managers().find(x => x.id === id) || {};
  const {mine, avg} = mgrStats(m);
  $('#m-title').textContent = m.name || id;
  $('#m-sub').textContent = (m.role||'')+' · '+mine.length+' контактов'+
    (avg!==null ? ' · средний балл '+avg.toFixed(1) : '')+(fb.telegram ? ' · '+fb.telegram : '');
  $('#m-body').innerHTML = coachBody(id);
  $('#modal').showModal();
}
registerTab({ id: 'managers', label: 'Команда', render: renderManagers });
