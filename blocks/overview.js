/* Блок «Обзор». Подключается сборщиком: scripts/build_cabinet.py */
/* ---------------------------- ОБЗОР ---------------------------- */
function renderOverview(){
  const contacts = DataSource.contacts(), leads = DataSource.leads(), sc = DataSource.scores();
  const items = sc ? (sc.items || sc.calls || []) : [];
  const avg = items.length ? (items.reduce((a,c)=>a+(c.total||0),0)/items.length).toFixed(1) : null;
  const won = leads.filter(l => l.stage === 'closed_won').length;
  const lost = leads.filter(l => l.stage === 'closed_lost').length;
  const conv = (won+lost) ? Math.round(won/(won+lost)*100) : 0;

  let html = '<div class="grid">'+
    kpi('Коммуникаций', contacts.length, DataSource.calls().length+' звонков · '+DataSource.chats().length+' переписок')+
    kpi('Разобрано', items.length || '—', items.length ? 'по вашей матрице' : 'аналитика не собрана')+
    kpi('Средний балл', avg ?? '—', avg ? 'из 10' : '')+
    kpi('Лидов', leads.length, '')+
    kpi('Конверсия', conv+'%', won+' выиграно / '+lost+' проиграно')+
  '</div>';

  const fn = DataSource.funnel();
  if(fn.length){
    html += '<h2>Воронка · коммуникации склеиваются по этапам</h2><div class="funnel">';
    fn.forEach(s => {
      const n = contacts.filter(c => c.stage === s.id).length;
      html += '<div class="fstep'+(s.id===CFG.focus_stage?' focus':'')+'"><b>'+esc(s.label)+'</b>'+
        '<p>'+esc(s.goal||'')+'</p>'+
        '<p style="margin-top:8px"><span class="pill'+(s.id===CFG.focus_stage?' accent':'')+'">'+n+' контактов</span></p></div>';
    });
    html += '</div>';
  }

  const mx = CFG.matrix || {extract:[],evaluate:[]};
  if((mx.evaluate||[]).length){
    html += '<h2>Матрица · что система достаёт из каждого контакта</h2><div class="two">';
    html += '<div class="card"><div class="kpi-label">Слой 1 · извлекаем факты</div>';
    (mx.extract||[]).forEach(e => html += '<div class="crit"><span>'+esc(e.label)+'</span>'+
      '<span class="muted small" style="max-width:55%;text-align:right">'+esc(e.note||'')+'</span></div>');
    html += '</div><div class="card"><div class="kpi-label">Слой 2 · оцениваем работу</div>';
    (mx.evaluate||[]).forEach(e => html += '<div class="crit"><span>'+esc(e.name)+'</span>'+
      '<span class="muted small" style="max-width:55%;text-align:right">'+esc(e.includes||'')+'</span></div>');
    html += '</div></div>';
  } else {
    html += '<h2>Матрица оценки</h2>'+emptyBlock('Матрица ещё не настроена',
      'Кабинет не знает, что считать хорошим разговором в вашем бизнесе.','шага 0');
  }

  if((CFG.questions||[]).length){
    html += '<h2>Вопросы, на которые отвечает кабинет</h2><div class="card">';
    CFG.questions.forEach((q,i) => html += '<div class="crit"><span>'+(i+1)+'. '+esc(q)+'</span></div>');
    html += '</div>';
  }
  return html;
}
registerTab({ id: 'overview', label: 'Обзор', render: renderOverview });
