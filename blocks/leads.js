/* Блок «Лиды». Подключается сборщиком: scripts/build_cabinet.py */
/* ---------------------------- ЛИДЫ ---------------------------- */
function renderLeads(){
  const enr = DataSource.enrichment();
  /* Сверху — сделки, где недавно разговаривали: с них начинается работа. */
  const act = {}; DataSource.contacts().forEach(c => act[c.lead_id] = c.when);
  const leads = DataSource.leads().slice().sort((a,b) =>
    (act[b.id] ? new Date(act[b.id]) : 0) - (act[a.id] ? new Date(act[a.id]) : 0));
  const isB2C = CFG.profile === 'b2c';
  let html = '<table><thead><tr>'+
    '<th>'+(isB2C?'Родитель':'Компания')+'</th><th>'+(isB2C?'Возраст':'Контакт')+'</th>'+
    '<th>Источник</th><th>Коммуникации</th><th>Этап</th><th>Сумма</th>'+
    '<th>'+(isB2C?'Реакция, мин':'След. шаг')+'</th><th></th></tr></thead><tbody>';
  leads.forEach(l => {
    const e = enr ? (enr.leads||[]).find(x => x.id === l.id) : null;
    html += '<tr class="clickable" onclick="openLead(\''+l.id+'\')">'+
      '<td>'+esc(l.company || l.parent)+'</td>'+
      '<td>'+esc(isB2C ? l.child_age+' лет' : (l.contact||''))+'</td>'+
      '<td class="muted">'+esc(l.source)+'</td>'+
      '<td>'+dealStrip(l.id)+'</td>'+
      '<td><span class="pill">'+esc(stageLabel(l.stage))+'</span></td>'+
      '<td>'+money(l.value_kzt)+'</td>'+
      '<td class="muted">'+(isB2C ? (l.responded_in_min ?? '—')
        : closed(l.stage) ? '—' : (l.next_step || '<span class="pill bad">нет</span>'))+'</td>'+
      '<td>'+(e ? '<span class="pill good">обогащён</span>' : '')+'</td></tr>';
  });
  html += '</tbody></table>';
  if(!enr) html += '<h2>Обогащение</h2>'+emptyBlock('Карточки пока сырые',
    'Кабинет знает только то, что записал менеджер. Внешнего контекста о клиенте нет.','шага 3');
  return html;
}
function openLead(id){
  const l = DataSource.leads().find(x => x.id === id);
  if(!l) return;
  const enr = DataSource.enrichment();
  const e = enr ? (enr.leads||[]).find(x => x.id === id) : null;
  $('#m-title').textContent = l.company || l.parent;
  $('#m-sub').textContent = stageLabel(l.stage)+' · '+money(l.value_kzt)+' · источник: '+l.source;
  let body = '<div class="card" style="margin-bottom:16px">';
  Object.entries(l).forEach(([k,v]) => { if(k!=='id')
    body += '<div class="crit"><span class="muted">'+esc(k)+'</span><span>'+esc(v ?? '—')+'</span></div>'; });
  body += '</div>';
  if(e){
    if(e.context) body += '<h2 style="margin-top:0">Контекст</h2><div class="card">'+esc(e.context)+'</div>';
    if(e.message) body += '<h2>Сообщение</h2><div class="card" style="white-space:pre-wrap">'+esc(e.message)+'</div>';
  }
  /* Путь сделки: коммуникации, склеенные по этапам. Разговор открывается кликом. */
  body += '<h2>Путь сделки</h2>'+dealThread(id);
  $('#m-body').innerHTML = body;
  $('#modal').showModal();
}
/* У закрытой сделки следующего шага не бывает — красное «нет» здесь врёт. */
const closed = st => { const f = DataSource.funnel().map(x => x.id || x);
  return f.length > 2 && f.slice(-2).indexOf(st) >= 0 };
registerTab({ id: 'leads', label: 'Лиды', render: renderLeads });
