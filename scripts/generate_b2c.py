#!/usr/bin/env python3
"""Генератор B2C-датасета для онлайн-школы CodeKids.

Профили менеджеров и связь скорости реакции с исходом заложены вероятностями
(см. data/b2c/PROFILE.md). Речь «грязная»: родители отвечают на ходу,
с детьми на фоне, часто пишут в WhatsApp вместо разговора.

Запуск:  python3 scripts/generate_b2c.py
"""

import json, random, pathlib
from datetime import datetime, timedelta

random.seed(20092026)
ROOT = pathlib.Path(__file__).resolve().parent.parent

MGRS = {
  "m1": dict(name="Алия Жумабаева",   asks_first=.75, value_first=.70, books=.78, obj="solve",    filler=.20),
  "m2": dict(name="Ерлан Касымов",    asks_first=.20, value_first=.10, books=.30, obj="features", filler=.30),
  "m3": dict(name="Динара Ускенбаева",asks_first=.92, value_first=.85, books=.88, obj="solve",    filler=.15),
  "m4": dict(name="Тимур Ниязов",     asks_first=.30, value_first=.15, books=.35, obj="avoid",    filler=.40),
}

MOTIVE = {
  "Чтобы увлёкся": dict(
    child=["Одиннадцать. В Minecraft целыми днями, моды какие-то ставит.",
           "Десять лет. В школе информатика есть, но ему там скучно.",
           "Двенадцать. Играет много, хочу перевести это во что-то полезное.",
           "Девять. Всё время в телефоне, если честно."],
    goal=["Хочу, чтобы он что-то создавал, а не только играл.",
          "Главное — чтобы увлёкся. Олимпиады потом.",
          "Пусть попробует, может, зацепит."]),
  "Профессия будущего": dict(
    child=["Четырнадцать. Думаем про профильный класс.",
           "Пятнадцать, надо уже определяться с направлением.",
           "Тринадцать. Математику любит, хочу развивать."],
    goal=["Нам важно, чтобы было портфолио к поступлению.",
          "Хочу, чтобы это была база для профессии, а не кружок.",
          "Интересуют олимпиады и реальные проекты."]),
  "Ребёнок попросил": dict(
    child=["Двенадцать. Сам нашёл ваш сайт и попросил записать.",
           "Десять, друг ходит, он тоже хочет.",
           "Тринадцать, она сама про дизайн интерфейсов говорит."],
    goal=["Не хочу сорвать интерес, поэтому спрашиваю подробно.",
          "Он сам загорелся, главное — правильный уровень подобрать."]),
  "Занять время": dict(
    child=["Одиннадцать. После школы свободен, надо чем-то занять.",
           "Девять, сидит один до вечера, я на работе."],
    goal=["Главное — расписание, чтобы совпало с другими кружками.",
          "Нужно что-то регулярное, чтобы не болтался."]),
}

SOURCES = ["Instagram","Instagram","Таргет","Поиск Google","Рекомендация","YouTube"]
PARENTS_F = ["Гульмира","Асель","Динара","Ержан","Сауле","Алма","Мадина","Айгуль","Нурлан","Жанна",
 "Балжан","Рустем","Индира","Талгат","Назгуль","Айжан","Ерболат","Ольга","Санжар","Айнур",
 "Максат","Арман","Камила","Даурен","Жулдыз","Ильяс","Аружан","Бауыржан","Мадияр","Аягоз"]
PARENTS_L = ["Абишева","Саутов","Турсынова","Ескендирова","Кабылов","Мукашева","Оспанова","Алиев",
 "Бекенова","Жумагулов","Каримова","Сагындыков","Айтпаева","Жанибеков","Ибрагимов","Нурпеисова",
 "Мамбетов","Ержанова","Токтаров","Сарсенова","Калиева","Оразбаев","Аманова","Кусаинов"]
DIRECTIONS = ["Программирование","Робототехника","Разработка игр","Дизайн","Визуальное программирование"]

F_MGR = ["ну","смотрите","так","в общем","э-э","да, и ещё"]
F_CLI = ["ну","э-э","как сказать","честно говоря","в принципе"]

GREET = [
 "{n}, здравствуйте, это {m} из CodeKids. Вы оставляли заявку {ago} — удобно говорить?",
 "{n}, добрый день! {m}, школа CodeKids. Пару минут есть?",
 "Здравствуйте, {n}. Это {m} из CodeKids, по вашей заявке.",
]
GREET_WEAK = [
 "Алло, добрый день, CodeKids беспокоит.",
 "Здравствуйте, вы заявку оставляли на курсы. Актуально ещё?",
 "Алло, это по поводу курсов программирования.",
]
ACK = ["Да, удобно.","Да, слушаю.","Угу, говорите.","Да-да.","Секунду, я выйду... всё, говорите.",
 "Я сейчас за рулём, но слушаю.","Да, только недолго, ребёнка забирать."]
NOISE = ["Подождите, ребёнок кричит... так, всё.","Извините, я на работе, говорите коротко.",
 "Секунду... да, я тут."]
Q_CHILD = ["Скажите, сколько лет ребёнку и что он уже пробовал?","Сколько ребёнку лет?",
 "Расскажите про ребёнка — чем увлекается?"]
Q_GOAL = ["А для вас что важнее — чтобы увлёкся или чтобы к олимпиадам готовился?",
 "Что вы хотите получить в итоге?","А почему решили именно программирование?"]
Q_DM = ["Решение по курсам принимаете вдвоём с супругом?","Кто ещё участвует в решении?",
 "С кем ещё будете обсуждать?"]
A_DM = ["Да, муж обычно решает по деньгам.","Я решаю, он не вмешивается.",
 "Вдвоём, но последнее слово за мужем.","Сама решаю."]
VALUE = [
 "У нас как раз есть курс, где дети пишут свои моды на Python — результат он увидит на первом же занятии.",
 "Группы до шести человек, преподаватель успевает к каждому. Это принципиально для первого курса.",
 "В конце курса ребёнок защищает свой проект — это то, что можно показать и в школе, и при поступлении.",
 "Начинаем не с текстового кода, а с блоков — логика настоящая, но подана понятно для его возраста.",
 "Если пропускает занятие, запись остаётся в кабинете, плюс преподаватель даёт разбор на следующем.",
]
FEATURES = [
 "У нас три направления: программирование, робототехника и разработка игр.",
 "Занятия два раза в неделю по сорок минут, курс тридцать два занятия.",
 "Есть личный кабинет, там родитель видит прогресс.",
 "Преподаватели практикующие, все с опытом в разработке.",
]
PRICE_Q = ["А сколько стоит?","Сколько это будет стоить?","Цена какая?","И во сколько нам это обойдётся?"]
PRICE_A = ["Программирование двести восемьдесят тысяч за курс, робототехника триста двадцать.",
 "Курс двести восемьдесят, это тридцать два занятия на полгода.",
 "Двести шестьдесят за дизайн, триста двадцать за робототехнику."]
OBJ = ["Ого. Это дорого для нас.","Нашли дешевле, за сто восемьдесят.","Надо с мужем посоветоваться.",
 "У нас плотное расписание: музыка, плавание.","А если он бросит через месяц?",
 "Боюсь, рано ему ещё.","Я подумаю и напишу."]
OBJ_ANS = {
 "solve":["Скажите, какая сумма в месяц для вас комфортна? Курс можно разбить на шесть платежей без переплаты.",
   "Давайте посмотрим расписание: есть вторник вечером и суббота утром. Что из этого попадает в ваши окна?",
   "Если бросит — платите только за пройденные месяцы, остаток отменяем. За два года так было у трёх семей из ста.",
   "Приходите на пробный, преподаватель посмотрит и честно скажет, рано или нет. Если рано — я сама вам это скажу.",
   "Предлагаю пробный в выходной, чтобы супруг тоже мог посмотреть минут десять. Так ему будет понятнее, за что платить."],
 "features":["У нас качество выше и преподаватели сильнее.","Зато группы маленькие и программа авторская.",
   "Есть рассрочка.","Ну это же на полгода, если посчитать за занятие — недорого."],
 "avoid":["Хорошо, думайте.","Понятно, тогда напишите, как решите.","Ладно, я на связи."]}
CLOSE_BOOK = [
 "Предлагаю бесплатный пробный урок {day} в {time} — сорок минут, ребёнок за занятие соберёт свой первый проект. Подходит?",
 "Записываю на пробный {day} в {time}? Ссылку пришлю в WhatsApp и напомню за час.",
 "Давайте {day} в {time} — посмотрите вместе, как он реагирует, и решите уже предметно.",
]
CLOSE_WEAK = ["Хорошо, думайте, обращайтесь.","Тогда напишите, если решите.","Ладно, всего доброго.",
 "Я тогда пришлю информацию в WhatsApp."]
CLI_YES = ["Да, давайте.","Хорошо, записывайте.","Давайте попробуем.","Да, четверг подходит."]
CLI_NO  = ["Я подумаю и напишу.","Надо посоветоваться.","Спасибо, мы пока присматриваемся.","Ладно, спасибо."]

def filler(who,p): return (random.choice(F_MGR if who=="manager" else F_CLI)+", ") if random.random()<p else ""
def say(who,text,p):
    f=filler(who,p)
    return text if not f else f+(text[0].lower()+text[1:] if text[:1].isupper() else text)

def build_call(mid, stage, lead, idx, dt, motive):
    m=MGRS[mid]; t=[]; said=set()
    add=lambda w,x: t.append({"who":w,"text":x})
    def pick(pool):
        fresh=[x for x in pool if x not in said] or pool
        x=random.choice(fresh); said.add(x); return x
    M=MOTIVE[motive]
    fast = lead["responded_in_min"] <= 20
    add("manager", (random.choice(GREET) if random.random()<m["asks_first"]+.2 else random.choice(GREET_WEAK))
        .format(n=lead["parent"].split()[0], m=m["name"].split()[0],
                ago=("двадцать минут назад" if fast else "вчера")))
    add("client", random.choice(NOISE if random.random()<.2 else ACK))

    asks = random.random() < m["asks_first"]
    if asks:
        add("manager", say("manager", pick(Q_CHILD), m["filler"]))
        add("client", say("client", pick(M["child"]), .3))
        add("manager", say("manager", pick(Q_GOAL), m["filler"]))
        add("client", say("client", pick(M["goal"]), .3))
        if random.random() < .45:
            add("manager", say("manager", pick(Q_DM), m["filler"]))
            add("client", say("client", random.choice(A_DM), .2))
    if random.random() < m["value_first"]:
        add("manager", pick(VALUE)); add("client", random.choice(["О, это ему было бы интересно.","Интересно.","Хорошо."]))
    else:
        add("manager", say("manager", pick(FEATURES), m["filler"])); add("client", random.choice(["Понятно.","Угу.","Ага."]))

    if random.random() < .8:
        add("client", random.choice(PRICE_Q)); add("manager", random.choice(PRICE_A))
        if random.random() < .7:
            add("client", random.choice(OBJ)); add("manager", random.choice(OBJ_ANS[m["obj"]]))

    booked = random.random() < m["books"]
    if booked:
        add("manager", random.choice(CLOSE_BOOK).format(
            day=random.choice(["в четверг","в субботу","во вторник","завтра"]),
            time=random.choice(["17:00","11:00","18:00","12:00"])))
        add("client", random.choice(CLI_YES))
    else:
        add("manager", random.choice(CLOSE_WEAK)); add("client", random.choice(CLI_NO))

    outcome = ("мотив выяснен, записаны на пробный" if asks and booked else
               "записаны на пробный без выяснения мотива" if booked else
               "цена названа без ценности, ушли думать" if not asks else
               "мотив выяснен, но до записи не дошли")
    return {"id":f"c{idx:03d}","date":dt.isoformat(timespec="minutes"),"manager_id":mid,
            "lead_id":lead["id"],"stage":stage,"direction":random.choice(["outbound","outbound","inbound"]),
            "duration_min":max(2,int(len(t)*random.uniform(.8,1.6))),"outcome":outcome,"transcript":t}

CH = {
 "good":[("manager","{n}, записала {ch} на {day} в 17:00. Вот ссылка на занятие."),
   ("manager","Два момента, чтобы урок прошёл хорошо: наушники и тихая комната."),
   ("client","Спасибо! А если он стесняется говорить?"),
   ("manager","Это нормально, в первые десять минут почти все молчат. Говорить необязательно — можно писать в чат."),
   ("client","Хорошо, успокоили."),
   ("manager","Напоминаю: завтра в 17:00, ссылка та же."),
   ("client","Он в восторге! Сам собрал проект, показывает всем."),
   ("manager","Отлично! Завтра пришлю отчёт преподавателя и варианты групп под его уровень.")],
 "price":[("manager","{n}, как вам пробное занятие? Готов оформить место в группе."),
   ("client","Понравилось, но дорого для нас."),("manager","Есть рассрочка на шесть месяцев."),
   ("client","Всё равно двести восемьдесят в сумме. Нашли за сто восемьдесят."),
   ("manager","У нас группы до шести человек и практикующие преподаватели."),
   ("client","Понятно, спасибо, мы подумаем.")],
 "solve":[("manager","{n}, отправила ссылку на оплату и расписание вторник-суббота."),
   ("client","Спасибо. Ещё думаю — боюсь, не потянем по нагрузке."),
   ("manager","Понимаю. Давайте так: первый месяц смотрим по самочувствию. Если тяжело — переводим на одно занятие в неделю без доплат и без потери места."),
   ("client","А так можно?"),
   ("manager","Да, мы так делаем для всех, у кого плотное расписание. Про это редко спрашивают, поэтому сама говорю."),
   ("client","Оплатили. Спасибо за честность.")],
 "silent":[("manager","Добрый день! Ссылка на пробное занятие завтра в 16:00."),
   ("client","Ок."),("manager","Вы не подключились к занятию. Перенести?"),
   ("client","Да, давайте потом."),("manager","Хорошо, напишите, когда будет удобно.")],
 "pricelist":[("client","Здравствуйте, сколько стоят занятия?"),
   ("manager","Здравствуйте! Программирование 280 000 ₸, робототехника 320 000 ₸, дизайн 260 000 ₸."),
   ("client","А сколько занятий?"),("manager","32 занятия, полгода."),
   ("client","Спасибо."),("manager","Обращайтесь!")],
}

def build_chat(mid, lead, idx, dt, kind):
    n=lead["parent"].split()[0]; msgs=[]; cur=dt
    for who,text in CH[kind]:
        cur += timedelta(minutes=random.randint(15,720))
        msgs.append({"who":who,"ts":cur.isoformat(timespec="minutes"),
                     "text":text.format(n=n, ch=random.choice(["сына","дочку","ребёнка"]),
                                        day=random.choice(["четверг","субботу","вторник"]))})
    outcome={"good":"родитель подготовлен к пробному, пришли вовремя",
             "price":"возражение по цене ушло в переписку и там умерло",
             "solve":"снято возражение по нагрузке, оплата прошла",
             "silent":"не пришли на пробный, причина не выяснена",
             "pricelist":"прайс вместо диалога, интерес не проверен"}[kind]
    return {"id":f"ch{idx:03d}","channel":random.choice(["whatsapp","whatsapp","whatsapp","telegram"]),
            "manager_id":mid,"lead_id":lead["id"],
            "stage":random.choice(["new","qualified","trial_booked","trial_done","payment"]),
            "date_start":dt.isoformat(timespec="minutes"),"date_end":msgs[-1]["ts"],
            "messages_count":len(msgs),"outcome":outcome,"messages":msgs}

def main():
    src=json.loads((ROOT/"data/b2c/dataset.json").read_text(encoding="utf-8"))
    leads=list(src["leads"]); start=datetime(2026,7,1,9,0)
    idx=len(leads)
    while idx < 260:
        idx+=1
        resp=random.choices([6,9,12,15,18,25,35,45,60,90,150,210,300],
                            weights=[8,10,12,12,10,9,8,7,6,6,5,4,3])[0]
        # скорость реакции влияет на исход — заложено специально
        if resp<=20:  stage=random.choices(["closed_won","payment","trial_done","trial_booked","qualified","closed_lost"],weights=[26,14,16,18,16,10])[0]
        elif resp<=60:stage=random.choices(["closed_won","payment","trial_done","trial_booked","qualified","closed_lost"],weights=[14,10,14,18,22,22])[0]
        else:         stage=random.choices(["closed_won","payment","trial_done","trial_booked","qualified","closed_lost","new"],weights=[5,5,8,12,20,40,10])[0]
        leads.append({"id":f"l{idx:02d}","parent":f"{random.choice(PARENTS_F)} {random.choice(PARENTS_L)}",
          "child_age":random.randint(8,16),"interest":random.choice(DIRECTIONS),
          "source":random.choice(SOURCES),
          "created":(start+timedelta(days=random.randint(0,75),hours=random.randint(0,10))).isoformat(timespec="minutes"),
          "responded_in_min":resp,"stage":stage,
          "value_kzt":random.choice([240000,260000,280000,280000,320000,320000,532000])})

    calls=list(src["calls"]); chats=list(src["chats"]); cid=len(calls); chid=len(chats)
    STAGES=["new","qualified","qualified","trial_booked","trial_done","payment","closed_won","closed_lost"]
    for _ in range(150):
        cid+=1; lead=random.choice(leads)
        mid=random.choices(list(MGRS),weights=[28,26,26,20])[0]
        dt=start+timedelta(days=random.randint(0,78),hours=random.randint(0,10),minutes=random.choice([0,5,10,15,20,25,30,40,45,50]))
        calls.append(build_call(mid,random.choice(STAGES),lead,cid,dt,random.choice(list(MOTIVE))))
    for _ in range(60):
        chid+=1; lead=random.choice(leads)
        mid=random.choices(list(MGRS),weights=[28,26,26,20])[0]
        kind={"m1":"solve","m2":"price","m3":"good","m4":"silent"}[mid] if random.random()<.6 \
             else random.choice(list(CH))
        dt=start+timedelta(days=random.randint(0,76),hours=random.randint(0,9))
        chats.append(build_chat(mid,lead,chid,dt,kind))

    calls.sort(key=lambda c:c["date"]); chats.sort(key=lambda c:c["date_start"])
    src["calls"],src["chats"],src["leads"]=calls,chats,leads
    (ROOT/"data/b2c/dataset.json").write_text(json.dumps(src,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"B2C: {len(calls)} звонков, {len(chats)} переписок, {len(leads)} лидов")

if __name__=="__main__":
    main()
