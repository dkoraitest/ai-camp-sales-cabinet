/* Блок «Менеджер». Подключается сборщиком: scripts/build_cabinet.py */
/* -------------------------- РАБОЧЕЕ МЕСТО МЕНЕДЖЕРА -------------------------- */
/* Один разбор, два взгляда: руководитель видит отдел, менеджер — себя.
   Здесь всё про одного человека, которого он выбрал в «Я».              */
function myLeads(){ const id = me(); return DataSource.leads().filter(l => ownerOf(l) === id) }
function lastTouch(id){
  const cs = DataSource.contacts().filter(c => c.lead_id === id);
  return cs.length ? new Date(cs[cs.length-1].when) : null;
}

/* ── Мои сделки (B2B) / Моя очередь (B2C) ── */
function renderMyDeals(){
  const b2c = isB2C(), now = dataNow();
  const all = myLeads(), open = all.filter(l => !closedStage(l.stage));
  if(!all.length) return emptyBlock('За вами пока нет '+(b2c?'заявок':'сделок'),
    'В базе нет поля «ответственный» или выбран человек без портфеля. Выберите другого в списке «Я».', 'шага 0');

  if(b2c){
    // Сколько клиент ждёт нас: с последнего разговора, а если его не было — с заявки.
    // Колонки из общих полей базы: у школы это «интерес», у клиники — «сегмент».
    const rows = open.map(l => { const lt = lastTouch(l.id);
      const from = lt || (l.created ? new Date(l.created) : null);
      return {l, r: leadScore(l), lt, wait: from ? daysBetween(from, now) : null} })
      .sort((a,b) => (!!touch(b.l.id) - !!touch(a.l.id)) || ((b.r&&b.r.score)||0) - ((a.r&&a.r.score)||0) || (b.wait||0) - (a.wait||0));
    const extra = l => l.interest || l.industry || '—';
    const extraLbl = open.some(l => l.interest) ? 'Интерес' : 'Сегмент';
    return '<div class="grid" style="margin-bottom:14px">'+
      kpi('В очереди', open.length, 'открытых заявок')+
      kpi('Приоритет A', rows.filter(x => x.r && x.r.grade === 'A').length, 'звонить сегодня')+
      kpi('Без ответа', rows.filter(x => !x.lt).length, 'ещё не было разговора')+
      kpi('Ждут дольше 3 дней', rows.filter(x => x.wait > 3).length, 'с последнего касания')+'</div>'+
      '<p class="scope">Сверху — заявки, которые скорее всего купят, если позвонить сейчас. Приоритет считает код: свежесть, соответствие профилю и то, что клиент говорил в разговорах.</p>'+
      '<table><thead><tr><th>Клиент</th><th>'+extraLbl+'</th><th>Источник</th><th>Ждёт</th><th>Первый ответ</th><th>Приоритет</th></tr></thead><tbody>'+
      rows.map(x => '<tr class="clickable" onclick="openDeal(\''+x.l.id+'\')"><td>'+esc(leadName(x.l.id))+
        (touch(x.l.id) ? ' <span class="pill accent">ответ готов</span>' : '')+'</td>'+
        '<td class="muted">'+esc(extra(x.l))+'</td><td class="muted">'+esc(x.l.source||'—')+'</td>'+
        '<td class="'+(x.wait > 3 ? 'late' : 'muted')+'">'+(x.wait != null ? x.wait+' дн.'+(x.lt ? '' : ' · новая') : '—')+'</td>'+
        '<td class="muted">'+(x.l.responded_in_min != null ? x.l.responded_in_min+' мин' : '—')+'</td>'+
        '<td>'+scorePill(x.r)+'</td></tr>').join('')+'</tbody></table>';
  }

  const info = open.map(l => {
    const last = lastTouch(l.id), ns = l.next_step ? new Date(l.next_step) : null;
    return {l, last, ns, idle: last ? daysBetween(last, now) : null,
            late: ns && ns < now, stuck: last && daysBetween(last, now) > 14, r: leadScore(l)};
  });
  const sum = open.reduce((a,l) => a + (l.value_kzt||0), 0);
  const won = all.filter(l => l.stage === DataSource.funnel().map(x => x.id||x).slice(-2)[0]).length;
  let html = '<div class="grid" style="margin-bottom:6px">'+
    kpi('Сделок в работе', open.length, money(sum))+
    kpi('Застряли', info.filter(x => x.stuck).length, 'без контакта больше 14 дней')+
    kpi('Следующий шаг просрочен', info.filter(x => x.late).length, 'или его нет: '+info.filter(x => !x.ns).length)+
    kpi('Закрыто', won, 'выиграно из '+(all.length - open.length)+' закрытых')+'</div>';
  const stages = DataSource.funnel().map(x => x.id||x).filter(s => !closedStage(s));
  stages.forEach(st => {
    const rows = info.filter(x => x.l.stage === st)
      .sort((a,b) => (!!touch(b.l.id) - !!touch(a.l.id)) || (b.late - a.late) || (b.stuck - a.stuck) || (b.l.value_kzt||0) - (a.l.value_kzt||0));
    if(!rows.length) return;
    html += '<h2>'+esc(stageLabel(st))+' · '+rows.length+' · '+money(rows.reduce((a,x) => a + (x.l.value_kzt||0), 0))+'</h2><div class="card" style="padding:4px 6px">'+
      rows.map(x => '<div class="row-deal" onclick="openDeal(\''+x.l.id+'\')">'+
        '<div><b>'+esc(leadName(x.l.id))+'</b>'+(touch(x.l.id) ? ' <span class="pill accent">касание готово</span>' : '')+'<div class="muted small">'+esc([x.l.contact, x.l.position].filter(Boolean).join(', '))+'</div></div>'+
        '<div>'+money(x.l.value_kzt)+'</div>'+
        '<div class="'+(x.stuck ? 'late' : 'muted')+' small">'+(x.last ? 'контакт '+x.idle+' дн. назад' : 'разговоров нет')+'</div>'+
        '<div class="'+(x.late || !x.ns ? 'late' : 'muted')+' small">'+(x.ns ? (x.late ? 'шаг просрочен · ' : 'шаг · ')+fmtDate(x.l.next_step).slice(0,5) : 'следующего шага нет')+'</div>'+
        '<div>'+scorePill(x.r)+'</div></div>').join('')+'</div>';
  });
  return html;
}

/* ── Мои звонки: семь показателей в сравнении с командой ── */
function renderMyCalls(){
  const s = DataSource.scores(), id = me();
  if(!s) return emptyBlock('Разговоры ещё не разобраны', 'После разбора здесь появится ваша оценка по семи показателям рядом со средней по команде.', 'шага 1');
  const items = s.items || [], byId = {};
  DataSource.contacts().forEach(c => byId[c.id] = c);
  const mine = items.filter(i => byId[i.id] && byId[i.id].manager_id === id);
  if(!mine.length) return emptyBlock('У вас пока нет разобранных разговоров', 'Выберите в списке «Я» другого менеджера.', 'шага 1');
  const avgOf = (arr, key) => { const v = arr.map(i => (i.evaluate||[]).find(e => e.id === key)).filter(Boolean).map(e => e.value);
    return v.length ? v.reduce((a,b) => a+b, 0) / v.length : null };
  const keys = (mine[0].evaluate || []).map(e => ({id: e.id, name: e.name}));
  const tot = arr => arr.reduce((a,i) => a + i.total, 0) / arr.length;
  const my = tot(mine), team = tot(items);
  const ranks = DataSource.managers().map(m => { const x = items.filter(i => byId[i.id] && byId[i.id].manager_id === m.id);
    return {id: m.id, v: x.length ? tot(x) : -1} }).sort((a,b) => b.v - a.v);
  let html = '<div class="grid" style="margin-bottom:14px">'+
    kpi('Мой средний балл', my.toFixed(1), 'по '+mine.length+' разговорам')+
    kpi('Средний по команде', team.toFixed(1), 'все разговоры отдела')+
    kpi('Место в команде', (ranks.findIndex(r => r.id === id) + 1)+' из '+ranks.length, 'по среднему баллу')+'</div>';
  html += '<h2>Семь показателей: я и команда</h2><p class="scope">Полоса — ваш средний, риска — средний по отделу. Смотрите не на самую короткую полосу, а на самый большой разрыв с командой: он и есть фокус недели.</p><div class="card">'+
    keys.map(k => { const a = avgOf(mine, k.id), b = avgOf(items, k.id); if(a == null) return '';
      const gap = a - b;
      return '<div class="skill"><div class="lbl"><span>'+esc(k.name)+'</span><span class="muted">'+a.toFixed(1)+
        ' <span style="opacity:.7">· команда '+b.toFixed(1)+'</span> '+
        '<span class="'+(gap < -0.5 ? 'late' : gap > 0.5 ? '' : 'muted')+'" style="'+(gap > 0.5 ? 'color:var(--good)' : '')+'">'+
        (gap >= 0 ? '+' : '')+gap.toFixed(1)+'</span></span></div>'+
        '<div class="vs"><i class="" style="width:'+Math.round(a*10)+'%;background:var(--'+(grade(a,10)==='good'?'good':grade(a,10)==='warn'?'warn':'bad')+')"></i>'+
        '<b style="left:calc('+Math.round(b*10)+'% - 1px)"></b></div></div>' }).join('')+'</div>';
  const recent = mine.slice().sort((a,b) => new Date(byId[b.id].when) - new Date(byId[a.id].when)).slice(0, 12);
  html += '<h2>Последние разговоры</h2><table><thead><tr><th>Дата</th><th>Клиент</th><th>Канал</th><th>Этап</th><th>Балл</th><th>Итог</th></tr></thead><tbody>'+
    recent.map(i => { const c = byId[i.id];
      return '<tr class="clickable" onclick="openContact(\''+c.id+'\')"><td>'+fmtDate(c.when)+'</td><td>'+esc(leadName(c.lead_id))+'</td>'+
        '<td><span class="pill">'+esc(c.kind==='call'?'звонок':(c.channel||'переписка'))+'</span></td>'+
        '<td><span class="pill">'+esc(stageLabel(c.stage))+'</span></td>'+
        '<td><span class="pill '+grade(i.total,10)+'">'+i.total.toFixed(1)+'</span></td><td class="muted small">'+esc(c.outcome||'')+'</td></tr>' }).join('')+
    '</tbody></table>';
  return html;
}

/* ── Мой тренер ── */
function renderMyCoach(){
  const id = me(), coach = DataSource.coaching();
  const fb = coach ? (coach.managers||[]).find(x => x.id === id) : null;
  if(!fb) return emptyBlock(coach ? 'Разбора для вас в этот раз нет' : 'Тренер ещё не подключён',
    coach ? 'Подробный разбор пишется тем, у кого он изменит поведение. Карта навыков — во вкладке «Мои звонки».'
          : 'Здесь появится разбор ваших разговоров, тренировка под слабый навык и доставка в Telegram.', 'шага 2');
  let html = '';
  if((fb.skills||[]).length){
    html += '<div class="card" style="margin-bottom:14px"><div class="kpi-label">Карта навыков</div>'+
      fb.skills.map(s => '<div class="skill"><div class="lbl"><span>'+esc(s.name)+'</span><span class="muted">'+s.value+'/'+(s.max||10)+'</span></div>'+
        '<div class="bar '+grade(s.value,s.max||10)+'"><i style="width:'+Math.round(s.value/(s.max||10)*100)+'%"></i></div></div>').join('')+'</div>';
  }
  return html + coachBody(id, true);
}

registerTab({ id: 'my-deals', role: 'manager', label: () => isB2C() ? 'Моя очередь' : 'Мои сделки', render: renderMyDeals });
registerTab({ id: 'my-calls', role: 'manager', label: 'Мои звонки', render: renderMyCalls });
registerTab({ id: 'my-coach', role: 'manager', label: 'Мой тренер', render: renderMyCoach });
