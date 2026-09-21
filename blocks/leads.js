/* Блок «Лиды». Подключается сборщиком: scripts/build_cabinet.py */
/* ---------------------------- ЛИДЫ ---------------------------- */
function renderLeads(){
  const enr = DataSource.enrichment();
  const b2c = isB2C();
  /* Скоринг считает код при открытии кабинета, логика майского lead-scoring:
     B2B — здоровье сделки, B2C — приоритет заявки. Сверху — то, что требует
     внимания сейчас; закрытые сделки внизу. */
  const act = {}; DataSource.contacts().forEach(c => act[c.lead_id] = c.when);
  const rows = DataSource.leads().map(l => ({l, r: leadScore(l)}))
    .sort((a,b) => ((b.r ? 1 : 0) - (a.r ? 1 : 0)) || ((b.r||{}).score||0) - ((a.r||{}).score||0) ||
      (act[b.l.id] ? new Date(act[b.l.id]) : 0) - (act[a.l.id] ? new Date(act[a.l.id]) : 0));
  const open = rows.filter(x => x.r);
  const cnt = g => open.filter(x => x.r.grade === g).length;
  const sum = g => open.filter(x => x.r.grade === g).reduce((a,x) => a + (x.l.value_kzt||0), 0);
  let html = '<div class="grid" style="margin-bottom:6px">'+
    kpi(b2c ? 'Приоритет A' : 'Здоровые сделки', cnt('A'), b2c ? 'звонить сегодня' : money(sum('A')))+
    kpi(b2c ? 'Приоритет B' : 'Под вопросом', cnt('B'), b2c ? 'в течение двух дней' : money(sum('B')))+
    kpi(b2c ? 'Приоритет C' : 'В зоне риска', cnt('C'), b2c ? 'письмо или отказ' : money(sum('C')))+
    kpi('Открытых', open.length, 'из '+rows.length+(b2c ? ' заявок' : ' сделок'))+'</div>'+
    '<p class="scope">'+(b2c ? 'Приоритет заявки' : 'Здоровье сделки')+' 0–100 считает код: '+
      (b2c ? 'свежесть заявки, соответствие профилю, что клиент говорил в разговорах, скорость первого ответа.'
           : 'соответствие профилю, полнота BANT по всем разговорам, следующий шаг, вовлечённость и тишина.')+
      ' Без разговоров веса смещаются на профиль и свежесть. Наведите на оценку — будут причины.</p>';
  html += '<table><thead><tr>'+
    '<th>'+(b2c?'Клиент':'Компания')+'</th><th>'+(b2c?'Интерес':'Контакт')+'</th>'+
    '<th>Источник</th><th>Коммуникации</th><th>Этап</th><th>Сумма</th>'+
    '<th>'+(b2c?'Первый ответ':'След. шаг')+'</th><th>'+(b2c?'Приоритет':'Здоровье')+'</th><th></th></tr></thead><tbody>';
  rows.forEach(({l, r}) => {
    const e = enr ? (enr.leads||[]).find(x => x.id === l.id) : null;
    html += '<tr class="clickable" onclick="openLead(\''+l.id+'\')">'+
      '<td>'+esc(leadName(l.id))+(touch(l.id) ? ' <span class="pill accent">касание</span>' : '')+'</td>'+
      '<td class="muted">'+esc(b2c ? (l.interest || l.industry || '—') : (l.contact||''))+'</td>'+
      '<td class="muted">'+esc(l.source)+'</td>'+
      '<td>'+dealStrip(l.id)+'</td>'+
      '<td><span class="pill">'+esc(stageLabel(l.stage))+'</span></td>'+
      '<td>'+money(l.value_kzt)+'</td>'+
      '<td class="muted">'+(b2c ? (l.responded_in_min != null ? l.responded_in_min+' мин' : '—')
        : closed(l.stage) ? '—' : (l.next_step ? fmtDate(l.next_step).slice(0,5) : '<span class="pill bad">нет</span>'))+'</td>'+
      '<td>'+scorePill(r)+'</td>'+
      '<td>'+(e ? '<span class="pill good">обогащён</span>' : '')+'</td></tr>';
  });
  html += '</tbody></table>';
  return html;
}
function openLead(id){
  const l = DataSource.leads().find(x => x.id === id);
  if(!l) return;
  const enr = DataSource.enrichment();
  const e = enr ? (enr.leads||[]).find(x => x.id === id) : null;
  if(typeof openDeal === 'function') return openDeal(id);   // карточка сделки: до, разговоры, после
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
