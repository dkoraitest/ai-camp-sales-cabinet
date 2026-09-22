#!/usr/bin/env python3
"""Самопроверка импорта своих разговоров.

Файлы-примеры создаются на лету и не содержат реальных данных. Каждая
проверка — это находка тестов на реалистичных файлах: если она снова
сломается, этот файл скажет, какая именно.

    python3 tests/test_import.py
"""

import importlib.util, io, json, pathlib, shutil, sys, tempfile, unittest, zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("imp", REPO / "scripts" / "import_data.py")
imp = importlib.util.module_from_spec(spec); spec.loader.exec_module(imp)

PROFILE = {"company": "Qazaq Pack", "what_we_sell": "стрейч-плёнку и гофрокороба складам", "audience": "b2b",
           "type": "long", "crm": "none",
           "funnel": [{"id": "first_contact", "label": "Первый контакт"}, {"id": "samples", "label": "Образцы"},
                      {"id": "won", "label": "Первая отгрузка"}, {"id": "lost", "label": "Проиграна"}]}

FILES = {
    # звонок: «Спикер 2» — менеджер, называет компанию и себя
    "2026-09-15_звонок_Мега_Склад.txt": "Спикер 1: Алло.\nСпикер 2: Ерлан, добрый день! Это Айгуль, компания Qazaq Pack.\n"
                                        "Спикер 1: Да, говорите.\nСпикер 2: Сколько плёнки уходит в месяц?\nСпикер 1: Две тонны.\n",
    # входящий: здесь менеджер — «Спикер 1», клиентку он тоже называет по имени
    "2026-09-17_входящий_Тенгри_Фуд.txt": "Спикер 1: Qazaq Pack, Марат, добрый день.\n"
                                           "Спикер 2: Это Асель, закупщик Тенгри Фуд. Нужны короба.\n"
                                           "Спикер 1: Асель, здравствуйте! Какие объёмы?\nСпикер 2: Восемь тысяч в месяц.\n",
    # WhatsApp с Android: системная строка, служебное сообщение, многострочное сообщение
    "Чат WhatsApp с Ерлан Мега Склад.txt": "15.09.26, 16:40 - Сообщения и звонки защищены сквозным шифрованием.\n"
                                           "15.09.26, 16:41 - Айгуль Жумабаева: Ерлан, добрый день! Пишу сюда.\n"
                                           "15.09.26, 16:52 - Ерлан Мега Склад: Жду КП\n"
                                           "18.09.26, 11:05 - Айгуль Жумабаева: <Без медиафайлов>\n"
                                           "18.09.26, 11:06 - Айгуль Жумабаева: Отправила КП:\n1) плёнка 23 мкм\n",
    # английский экспорт с айфона, латиница
    "wa_ios_en_12h.txt": "[9/21/26, 10:15:32 AM] Aigul Zhumabayeva: Hello Erlan, sending the offer\n"
                         "[9/21/26, 10:20:01 AM] Erlan Mega Sklad: Thanks, what about payment terms?\n",
    # Марат с другим клиентом — чтобы он был «менеджером с разными клиентами»
    "2026-09-19_Алтын_Групп.txt": "Марат Садыков: Добрый день, Qazaq Pack.\nБауыржан Тлеуов: Слушаю.\n"
                                  "Марат Садыков: Образцы получили?\nБауыржан Тлеуов: Да.\n",
    # заметки: «Итог:», «Участники:» — не говорящие
    "заметки.txt": "Встреча с Алтын Групп.\nУчастники: Бауыржан, Жанна.\nИтог: хотят расчёт.\n",
    # md с жирными метками и датой в заголовке
    "транскрипт_Нур_Фарм.md": "# Созвон с Нур Фарм, 2026-09-14\n\n**Асель Ким:** Данияр, добрый день! Qazaq Pack на связи.\n"
                              "**Данияр:** Добрый.\n**Асель Ким:** Сколько рулонов в месяц?\n**Данияр:** Сорок.\n",
    # три участника, один сказал одну реплику
    "2026-09-23_звонок_Береке.txt": "Айгуль Жумабаева: Серик, добрый день! Qazaq Pack, удобно?\n"
                                    "Серик Жаксылыков: Да, со мной финдиректор.\nГульнара Омарова: Здравствуйте, нас волнует отсрочка.\n"
                                    "Айгуль Жумабаева: Сколько паллет в месяц?\nСерик Жаксылыков: Около ста.\n",
    # сводка по клиентам: метки повторяются и чередуются, но это не разговор
    "сводка.txt": "Статус: Береке ждёт расчёт\nПримечание: отсрочка 30 дней\nСтатус: Шыгыс — отгрузка 25.09\n"
                  "Примечание: счёт на предоплату\n",
    # живые сообщения со словами, похожими на служебные
    "Чат WhatsApp с Серик Береке.txt": "23.09.26, 09:10 - Серик Жаксылыков: Айгуль, вижу пропущенный звонок от вас, наберу\n"
                                        "23.09.26, 09:11 - Айгуль Жумабаева: Хорошо, расчёт пришлю сюда.\n"
                                        "23.09.26, 09:12 - Айгуль Жумабаева: Пропущенный аудиозвонок\n"
                                        "23.09.26, 09:15 - Серик Жаксылыков: Контакт изменён у бухгалтера, пишите на новый номер\n",
    # филиал с похожим названием — не та же сделка
    "2026-09-24_звонок_Береке_Шымкент.txt": "Марат Садыков: Добрый день, это Марат, Qazaq Pack.\nКлиент: Мы отдельная компания.\n"
                                            "Марат Садыков: Какие объёмы у вас?\nКлиент: Полтонны в месяц.\n",
    # передача сделки: клиент говорит уже с другим менеджером
    "2026-09-25_звонок_Нур_Фарм_передача.txt": "Марат Садыков: Данияр, добрый день! Это Марат, Qazaq Pack, теперь я веду вашу сделку.\n"
                                               "Данияр: Добрый. Договор вы получили?\nМарат Садыков: Да, вернём с правками. Кто подписывает?\n"
                                               "Данияр: Генеральный.\n",
    # встреча с метками по одному имени: Марат — один на все записи, Асель — и менеджер, и клиентка
    "2026-09-20_встреча_Тенгри_Фуд.txt": "[00:00:05] Марат: Доброе утро! Как и обещал, принёс расчёт по списаниям.\n"
                                         "[00:00:21] Асель: Да, Ержан Болатович подключится через пару минут.\n"
                                         "[00:01:02] Ержан Болатович: Здравствуйте. Давайте сразу к цифрам.\n"
                                         "[00:01:10] Марат: Одно списание перекрывает разницу в цене за полгода.\n"
                                         "[00:02:30] Ержан Болатович: Хорошо, готовьте договор.\n"
                                         "[00:02:50] Гульжан Сапарова: Договор посмотрю до пятницы.\n",
    # в имени файла роль, а не компания; клиент назван полнее, чем в имени файла
    "2026-09-16_звонок_Мега_с_РОП.txt": "Айгуль Жумабаева: Ерлан, добрый день! Сколько плёнки уходит в месяц?\n"
                                        "Ерлан Мега Склад: Две тонны.\n"
                                        "Айгуль Жумабаева: Давайте я подключу руководителя, он согласует отсрочку.\n"
                                        "Нуржан РОП: Ерлан, добрый день, отсрочку 30 дней согласуем со второй поставки.\n"
                                        "Ерлан Мега Склад: Хорошо, договорились.\n",
    # «Мега» — начало двух названий: какого, скрипт не решает
    "2026-09-24_звонок_Мега_Склад_Астана.txt": "Марат Садыков: Добрый день, это Марат, Qazaq Pack.\n"
                                               "Клиент: Мы отдельная компания, в Астане.\nМарат Садыков: Какие объёмы?\n"
                                               "Клиент: Полтонны в месяц.\n",
    "2026-09-26_звонок_Мега.txt": "Айгуль Жумабаева: Добрый день, Qazaq Pack. Какой у вас склад?\nКлиент: Новый, пока без вывески.\n"
                                  "Айгуль Жумабаева: Сколько паллет в месяц?\nКлиент: Двадцать.\n",
    # одно слово, с которого начинается ровно одно название
    "короткий_звонок_Каспий.txt": "Менеджер: Руслан, добрый день, это Асель из Qazaq Pack, по КП звоню.\n"
                                  "Клиент: Асель, мы уже взяли у другого поставщика, извините. Всего доброго.\n",
    # Teams VTT с GUID
    "Teams_Каспий_Трейд_2026-09-18.vtt": "WEBVTT\n\n6c0b7c2e-4a1d/12-0\n00:00:03.120 --> 00:00:06.480\n"
                                         "<v Асель Ким>Руслан, добрый день!</v>\n\n6c0b7c2e-4a1d/13-0\n"
                                         "00:00:07.000 --> 00:00:11.250\n<v Руслан Ибраев>Добрый. Давайте по делу.</v>\n",
}


def docx(paragraphs):
    xml = ('<?xml version="1.0"?><w:document xmlns:w="w"><w:body>' +
           "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs) + "</w:body></w:document>")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", xml)
    return b.getvalue()


class ImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        root = cls.tmp
        (root / "data" / "import").mkdir(parents=True); (root / "active").mkdir(); (root / "cabinet").mkdir()
        (root / "active" / "profile.json").write_text(json.dumps(PROFILE, ensure_ascii=False), encoding="utf-8")
        src = root / "data" / "import"
        for name, text in FILES.items():
            (src / name).write_text(text, encoding="utf-8")
        # cp1251 и CSV из Excel: кавычки, «;» внутри поля, CRLF, дата с секундами
        (src / "звонки.csv").write_bytes(("Разговор;Дата;Говорящий;Текст\r\n"
            "call_101;12.09.2026 14:05:12;Оператор;Добрый день, Qazaq Pack, Айгуль.\r\n"
            'call_101;12.09.2026 14:05:20;Клиент;"Да, это Ерлан, Мега Склад; нужны короба."\r\n').encode("cp1251"))
        # docx в формате Teams/Word: имя и время строкой, реплика под ней; &amp; и мягкий перенос
        (src / "Тенгри_Фуд_встреча_2026-09-19.docx").write_bytes(docx([
            "Встреча Тенгри Фуд", "Марат Садыков   0:03", "Коллеги, P&amp;G тоже так пакует, начнём?",
            "Нурлан Серикович   0:09", "Да, давай­те."]))
        # архив WhatsApp с айфона
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("_chat.txt", "[20.09.2026, 10:00:00] Асель Нурланова: Марат, адрес склада прислала.\n"
                                    "[20.09.2026, 10:05:00] Марат Садыков: Спасибо, будем в среду.\n")
        (src / "WhatsApp Chat - Асель Нурланова.zip").write_bytes(b.getvalue())
        # тот же чат ещё и распакован рядом
        (src / "_chat.txt").write_text("[20.09.2026, 10:00:00] Асель Нурланова: Марат, адрес склада прислала.\n"
                                       "[20.09.2026, 10:05:00] Марат Садыков: Спасибо, будем в среду.\n", encoding="utf-8")
        # docx Teams: имя и время через табуляцию, реплика с переносом строки внутри
        (src / "Teams_таб_Береке.docx").write_bytes(docx([
            "Айгуль Жумабаева</w:t><w:tab/><w:t>0:03", "Коллеги, начнём?</w:t><w:br/><w:t>Плюс вопрос по срокам.",
            "Серик Жаксылыков</w:t><w:tab/><w:t>0:09", "Да, начинаем."]))
        # полный архив Telegram в папке экспорта: рабочий чат, «Мама», «Избранное»
        (src / "ChatExport_2026-09-20").mkdir()
        (src / "ChatExport_2026-09-20" / "result.json").write_text(json.dumps({"chats": {"list": [
            {"type": "saved_messages", "messages": [{"type": "message", "from": "Асель Ким", "text": "пароль от wifi"}]},
            {"name": "Мама", "type": "personal_chat", "messages": [
                {"type": "message", "date": "2026-09-20T09:00:00", "from": "Мама", "text": "Ты во сколько сегодня?"},
                {"type": "message", "date": "2026-09-20T09:01:00", "from": "Асель Ким", "text": "В 8"}]},
            {"name": "Руслан Каспий Трейд", "type": "personal_chat", "messages": [
                {"type": "message", "date": "2026-09-19T14:00:00", "from": "Асель Ким", "text": "Руслан, отправляю КП, как обсуждали."},
                {"type": "message", "date": "2026-09-19T14:10:00", "from": "Руслан Ибраев", "text": "Получил. Дорого."}]},
            {"id": 7, "name": "Руслан", "type": "personal_chat", "messages": [
                {"type": "message", "date": "2026-09-20T18:00:00", "from": "Руслан", "text": "Асель, в субботу на футбол идёшь?"},
                {"type": "message", "date": "2026-09-20T18:05:00", "from": "Асель Ким", "text": "Иду!"}]},
            {"id": 8, "name": "Руслан", "type": "personal_chat", "messages": [
                {"type": "message", "date": "2026-09-21T10:00:00", "from": "Асель Ким", "text": "Руслан, добрый день! Каспий Трейд, по плёнке пришлю расчёт."},
                {"type": "message", "date": "2026-09-21T10:05:00", "from": "Руслан", "text": "Спасибо, посмотрим цену."}]},
            # рабочие чаты без слов про деньги: сделка в названии чата и клиент сделки из других записей
            {"id": 9, "name": "Жанна Алтын Групп", "type": "personal_chat", "messages": [
                {"type": "message", "date": "2026-09-23T12:00:00", "from": "Айгуль Жумабаева", "text": "Жанна, добрый день! Удобно созвониться завтра в 11?"},
                {"type": "message", "date": "2026-09-23T12:05:00", "from": "Жанна Сапарова", "text": "Да, давайте, наберите."}]},
            {"id": 10, "name": "Бауыржан", "type": "personal_chat", "messages": [
                {"type": "message", "date": "2026-09-23T19:00:00", "from": "Марат Садыков", "text": "Бауыржан, добрый вечер! Завтра в силе?"},
                {"type": "message", "date": "2026-09-23T19:05:00", "from": "Бауыржан Тлеуов", "text": "Да, ждём."}]}]}},
            ensure_ascii=False), encoding="utf-8")
        (root / "blocks").mkdir(); (root / "scripts").mkdir()
        shutil.copy2(REPO / "blocks" / "config.template.js", root / "blocks" / "config.template.js")
        shutil.copy2(REPO / "scripts" / "build_data.py", root / "scripts" / "build_data.py")
        # после «включи демо»: эталонный конфиг демо-компании и привязки Telegram
        (root / "cabinet" / "config.js").write_text('window.CABINET_CONFIG = { profile: "b2b", company: "DataFlow Solutions", '
                                                    'focus_stage: "discovery", funnel: [] };', encoding="utf-8")
        (root / "active" / "telegram.json").write_text('{"m1": 111}', encoding="utf-8")
        (root / "cabinet" / "telegram.js").write_text('window.CABINET_TELEGRAM = {"bot": "demo_bot", "links": {"m1": true}};',
                                                      encoding="utf-8")
        imp.ROOT, imp.SRC = root, src
        imp.PARSED, imp.MAPPING, imp.DONE = src / "_parsed.json", src / "_mapping.json", src / "_done"
        imp.OWN, imp.CAB = root / "data" / "own", root / "cabinet"
        cls.out = io.StringIO(); stdout = sys.stdout; sys.stdout = cls.out
        try:
            imp.cmd_scan(None)
        finally:
            sys.stdout = stdout
        cls.mp = json.loads(imp.MAPPING.read_text(encoding="utf-8"))
        cls.parsed = {c["key"]: c for c in json.loads(imp.PARSED.read_text(encoding="utf-8"))}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def conv(self, key):
        return self.mp["conversations"][key]

    def mid(self, name):
        return next(k for k, v in self.mp["managers"].items() if v == name)

    # ── находки на реалистичных файлах ──
    def test_roles_per_conversation(self):
        """«Спикер 1» — клиент в исходящем и менеджер во входящем."""
        self.assertEqual(self.conv("2026-09-15_звонок_Мега_Склад.txt")["speakers"]["Спикер 1"], "client")
        self.assertEqual(self.conv("2026-09-15_звонок_Мега_Склад.txt")["speakers"]["Спикер 2"], self.mid("Айгуль Жумабаева"))
        self.assertEqual(self.conv("2026-09-17_входящий_Тенгри_Фуд.txt")["speakers"]["Спикер 1"], self.mid("Марат Садыков"))

    def test_latin_name_is_same_manager(self):
        self.assertEqual(self.conv("wa_ios_en_12h.txt")["speakers"]["Aigul Zhumabayeva"], self.mid("Айгуль Жумабаева"))
        self.assertEqual(self.conv("wa_ios_en_12h.txt")["speakers"]["Erlan Mega Sklad"], "client")

    def test_deals_are_merged(self):
        for key in ("2026-09-15_звонок_Мега_Склад.txt", "Чат WhatsApp с Ерлан Мега Склад.txt", "wa_ios_en_12h.txt",
                    "звонки.csv"):
            self.assertEqual(self.conv(key)["lead"], "Мега Склад", key)
        self.assertEqual(self.conv("WhatsApp Chat - Асель Нурланова.zip")["lead"], "Тенгри Фуд")
        self.assertEqual(self.conv("ChatExport_2026-09-20/result.json#Руслан Каспий Трейд")["lead"], "Каспий Трейд")

    def test_personal_chats_excluded(self):
        self.assertTrue(self.conv("ChatExport_2026-09-20/result.json#Мама")["exclude"])
        self.assertTrue(self.conv("ChatExport_2026-09-20/result.json#Избранное")["exclude"])
        self.assertFalse(self.conv("ChatExport_2026-09-20/result.json#Руслан Каспий Трейд")["exclude"])

    def test_notes_are_not_a_transcript(self):
        self.assertNotIn("заметки.txt", self.mp["conversations"])
        self.assertIn("заметки.txt", self.out.getvalue())

    def test_formats_and_cleanup(self):
        text = " ".join(t["text"] for c in self.parsed.values() for t in c["turns"])
        for bad in ("Без медиафайлов", "шифрованием", "&amp;", "­", "-->"):
            self.assertNotIn(bad, text)
        self.assertIn("P&G", text)
        self.assertIn("давайте", text)
        self.assertEqual(self.parsed["транскрипт_Нур_Фарм.md"]["date"][:10], "2026-09-14")
        self.assertEqual(set(self.parsed["Teams_Каспий_Трейд_2026-09-18.vtt"]["speakers"]), {"Асель Ким", "Руслан Ибраев"})
        self.assertIn("1) плёнка 23 мкм", " ".join(t["text"] for t in self.parsed["Чат WhatsApp с Ерлан Мега Склад.txt"]["turns"]))

    def test_rescan_keeps_edits_and_keys(self):
        mp = json.loads(imp.MAPPING.read_text(encoding="utf-8"))
        mp["conversations"]["2026-09-15_звонок_Мега_Склад.txt"]["outcome"] = "выслать КП"
        mp["leads"]["Мега Склад"] = {"result": "won", "value_kzt": 100}
        imp.MAPPING.write_text(json.dumps(mp, ensure_ascii=False), encoding="utf-8")
        (imp.SRC / "0000_новый_файл.txt").write_text("Айгуль Жумабаева: Добрый день, Qazaq Pack.\nКлиент: Слушаю.\n", encoding="utf-8")
        out, stdout = io.StringIO(), sys.stdout; sys.stdout = out
        try:
            imp.cmd_scan(None)
        finally:
            sys.stdout = stdout
        after = json.loads(imp.MAPPING.read_text(encoding="utf-8"))
        self.assertEqual(after["conversations"]["2026-09-15_звонок_Мега_Склад.txt"]["outcome"], "выслать КП")
        self.assertEqual(after["leads"]["Мега Склад"]["result"], "won")
        for k, v in mp["conversations"].items():
            self.assertEqual(after["conversations"][k]["lead"], v["lead"], k)

    def test_build_refuses_unknown_manager_and_moves_stale(self):
        mp = json.loads(imp.MAPPING.read_text(encoding="utf-8"))
        broken = json.loads(json.dumps(mp))
        broken["conversations"]["2026-09-15_звонок_Мега_Склад.txt"]["speakers"]["Спикер 2"] = "m?"
        imp.MAPPING.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(SystemExit):
            out, stdout = io.StringIO(), sys.stdout; sys.stdout = out
            try:
                imp.cmd_build(type("A", (), {"top_up": 0})())
            finally:
                sys.stdout = stdout
        imp.MAPPING.write_text(json.dumps(mp, ensure_ascii=False), encoding="utf-8")
        (imp.CAB / "coach.js").write_text("// прежняя база", encoding="utf-8")
        out, stdout = io.StringIO(), sys.stdout; sys.stdout = out
        try:
            imp.cmd_build(type("A", (), {"top_up": 0})())
        finally:
            sys.stdout = stdout
        self.assertFalse((imp.CAB / "coach.js").exists())
        d = json.loads((imp.OWN / "dataset.json").read_text(encoding="utf-8"))
        self.assertTrue(all(x.get("imported") for x in d["calls"] + d["chats"]))
        self.assertNotIn("Мама", {l["company"] for l in d["leads"]})
        cfg = (imp.CAB / "config.js").read_text(encoding="utf-8")
        self.assertIn('"Qazaq Pack"', cfg); self.assertIn('profile: "own"', cfg)
        self.assertFalse((imp.ROOT / "active" / "telegram.json").exists())
        self.assertIn('"links": {}', (imp.CAB / "telegram.js").read_text(encoding="utf-8"))


class RoundThree(ImportTest):
    """Находки третьего раунда: те же примеры, другие проверки."""

    def test_single_utterance_participant(self):
        self.assertIn("Гульнара Омарова", self.parsed["2026-09-23_звонок_Береке.txt"]["speakers"])
        # одна короткая фраза без вопроса и обращения, но подписана именем и фамилией
        self.assertIn("Гульжан Сапарова", self.parsed["2026-09-20_встреча_Тенгри_Фуд.txt"]["speakers"])

    def test_notes_with_repeating_labels_are_not_dialogue(self):
        self.assertNotIn("сводка.txt", self.mp["conversations"])

    def test_live_messages_are_kept(self):
        text = [t["text"] for t in self.parsed["Чат WhatsApp с Серик Береке.txt"]["turns"]]
        self.assertTrue(any("пропущенный звонок от вас" in x for x in text))
        self.assertTrue(any("Контакт изменён у бухгалтера" in x for x in text))
        self.assertNotIn("Пропущенный аудиозвонок", text)

    def test_same_named_chats_are_different(self):
        keys = [k for k in self.mp["conversations"] if k.startswith("ChatExport_2026-09-20/result.json#")]
        self.assertIn("ChatExport_2026-09-20/result.json#7", keys)
        self.assertIn("ChatExport_2026-09-20/result.json#8", keys)
        self.assertTrue(self.conv("ChatExport_2026-09-20/result.json#7")["exclude"])
        self.assertFalse(self.conv("ChatExport_2026-09-20/result.json#8")["exclude"])
        self.assertEqual(self.conv("ChatExport_2026-09-20/result.json#8")["lead"], "Каспий Трейд")

    def test_handover_client_stays_client(self):
        self.assertEqual(self.conv("2026-09-25_звонок_Нур_Фарм_передача.txt")["speakers"]["Данияр"], "client")
        self.assertEqual(self.conv("2026-09-25_звонок_Нур_Фарм_передача.txt")["lead"], "Нур Фарм")
        self.assertIn("Нур Фарм: Асель Ким → Марат Садыков", self.out.getvalue())

    def test_handover_owner_is_the_new_manager(self):
        out, stdout = io.StringIO(), sys.stdout; sys.stdout = out
        try:
            imp.cmd_build(type("A", (), {"top_up": 0})())
        finally:
            sys.stdout = stdout
        d = json.loads((imp.OWN / "dataset.json").read_text(encoding="utf-8"))
        lead = next(l for l in d["leads"] if l["company"] == "Нур Фарм")
        self.assertEqual(lead["owner"], self.mid("Марат Садыков"))

    def test_similar_company_is_not_merged(self):
        self.assertEqual(self.conv("2026-09-24_звонок_Береке_Шымкент.txt")["lead"], "Береке Шымкент")
        # «Береке» — начало «Береке Шымкент», но общего клиента нет: подсказка вместо склейки
        self.assertEqual(self.conv("2026-09-23_звонок_Береке.txt")["lead"], "Береке")
        self.assertEqual(self.conv("Чат WhatsApp с Серик Береке.txt")["lead"], "Береке")   # Серик — клиент Береке
        self.assertIn("«Береке» — «Береке Шымкент»?", self.out.getvalue())

    def test_docx_tab_layout_and_breaks(self):
        c = self.parsed["Teams_таб_Береке.docx"]
        self.assertEqual(set(c["speakers"]), {"Айгуль Жумабаева", "Серик Жаксылыков"})
        self.assertIn("Плюс", c["turns"][0]["text"])
        self.assertNotIn("начнём?Плюс", c["turns"][0]["text"])

    def test_first_name_label_is_manager_only_if_unique(self):
        c = self.conv("2026-09-20_встреча_Тенгри_Фуд.txt")
        self.assertEqual(c["speakers"]["Марат"], self.mid("Марат Садыков"))
        self.assertEqual(c["speakers"]["Асель"], "client")        # есть и Асель Ким, и Асель Нурланова
        self.assertEqual(c["speakers"]["Ержан Болатович"], "client")
        self.assertEqual(c["lead"], "Тенгри Фуд")
        self.assertIn("имени без фамилии", self.out.getvalue())

    def test_role_word_is_not_a_company(self):
        c = self.conv("2026-09-16_звонок_Мега_с_РОП.txt")
        self.assertEqual(c["lead"], "Мега Склад")
        self.assertEqual(c["speakers"]["Ерлан Мега Склад"], "client")
        self.assertNotEqual(c["speakers"]["Нуржан РОП"], "client")

    def test_prefix_merge_only_when_one_candidate(self):
        self.assertEqual(self.conv("2026-09-26_звонок_Мега.txt")["lead"], "Мега")
        self.assertEqual(self.conv("2026-09-24_звонок_Мега_Склад_Астана.txt")["lead"], "Мега Склад Астана")
        self.assertEqual(self.conv("короткий_звонок_Каспий.txt")["lead"], "Каспий Трейд")
        self.assertEqual(self.conv("звонки.csv")["lead"], "Мега Склад")    # «Мега» внутри «Мега Склад» не мешает

    def test_work_chat_without_money_words(self):
        for key in ("ChatExport_2026-09-20/result.json#9", "ChatExport_2026-09-20/result.json#10"):
            self.assertFalse(self.conv(key)["exclude"], key)
            self.assertEqual(self.conv(key)["lead"], "Алтын Групп", key)
        self.assertTrue(self.conv("ChatExport_2026-09-20/result.json#7")["exclude"])
        self.assertTrue(self.conv("ChatExport_2026-09-20/result.json#Мама")["exclude"])

    def test_duplicate_chat_taken_once(self):
        both = [k for k in ("WhatsApp Chat - Асель Нурланова.zip", "_chat.txt") if k in self.mp["conversations"]]
        self.assertEqual(len(both), 1)


class RoundFour(unittest.TestCase):
    """Находки четвёртого раунда: онлайн-школа, заявки от родителей и корпоративные клиенты."""
    PROFILE = {"company": "Qadam Academy", "what_we_sell": "курсы для детей и корпоративный английский",
               "audience": "b2c", "type": "flow", "crm": "none",
               "funnel": [{"id": "lead", "label": "Заявка"}, {"id": "trial", "label": "Пробное"},
                          {"id": "paid", "label": "Оплата"}, {"id": "lost", "label": "Отказ"}]}
    FILES = {
        # родители: одна — тёзка менеджера, другой — тёзка другого менеджера и записан одним именем
        "Чат WhatsApp с Гульмира мама Санжара.txt":
            "14.09.26, 19:02 - Гульмира мама Санжара: Здравствуйте! Оставляла заявку на курс программирования для сына.\n"
            "14.09.26, 19:10 - Динара Омарова: Гульмира, добрый вечер! Это Динара, школа Qadam. Санжар уже пробовал?\n"
            "14.09.26, 19:20 - Гульмира мама Санжара: Спасибо, Динара! А сколько стоит в месяц?\n"
            "14.09.26, 19:21 - Динара Омарова: 32 000 ₸ в месяц, первое занятие бесплатно.\n",
        "Чат WhatsApp с Динара мама Амира.txt":
            "15.09.26, 18:00 - Динара мама Амира: Добрый вечер, есть английский для 8 лет?\n"
            "15.09.26, 18:05 - Динара Омарова: Динара, добрый вечер! Да, группа по субботам.\n"
            "15.09.26, 18:07 - Динара мама Амира: Хорошо, запишите на пробное.\n",
        "WhatsApp Chat - Алибек.txt":
            "17.09.26, 20:14 - Алибек: Добрый вечер. Дочке 13 лет, хочет в веб-дизайн. Есть такое?\n"
            "17.09.26, 20:20 - Динара Омарова: Алибек, добрый вечер! Да, курс для 12–15 лет.\n"
            "17.09.26, 20:25 - Алибек: Сколько по деньгам?\n",
        # корпоративные клиенты
        "2026-09-08_звонок_Каратау_Агро.txt": "Алибек Нуртаев: Серик Маратович, добрый день! Qadam Academy, английский для команды.\n"
                                              "Серик Балтабаев: Добрый день. Нам нужно для десяти сотрудников.\n"
                                              "Алибек Нуртаев: Какой уровень у группы?\nСерик Балтабаев: Начальный.\n",
        "2026-09-11_встреча_Номад_Софт.txt": "Алибек Нуртаев: Жанар, добрый день! Давайте по программе.\n"
                                             "Жанар Мусина: Да, нам важны отчёты по прогрессу.\n"
                                             "Алибек Нуртаев: Отчёт каждый месяц. Подходит?\nЖанар Мусина: Подходит.\n",
        # одна компания латиницей, с Group и именем контакта впереди
        "2026-09-12_встреча_Сункар_Медиа.txt": "Самат Жаксылыков: Мадияр, добрый день! Qadam Academy.\n"
                                               "Мадияр Курманов: Добрый день. Нужен английский для продюсеров.\n"
                                               "Самат Жаксылыков: Сколько человек в группе?\nМадияр Курманов: Восемь.\n",
        "WhatsApp Chat with Madiyar Sunkar Media Group.txt":
            "9/18/26, 9:05 AM - Samat Zhaksylykov: Madiyar, good morning! Sending the program.\n"
            "9/18/26, 11:40 AM - Madiyar Kurmanov: Thanks. Our director wants a trial first\n"
            "9/18/26, 11:42 AM - Samat Zhaksylykov: Sure, a free trial on Tuesday. Does that work?\n",
        # рабочий чат с контактом одним именем
        "WhatsApp Chat - Серик.txt": "19.09.26, 10:00 - Самат Жаксылыков: Серик Маратович, договор отправил на почту.\n"
                                     "19.09.26, 10:30 - Серик: Договор подписан, первый платёж отправили.\n"
                                     "19.09.26, 10:31 - Самат Жаксылыков: Спасибо! Расписание пришлю в пятницу.\n",
        # похожая, но другая компания звучит в безымянном звонке
        "2026-09-19_звонок_Арман_Строй.txt": "Алибек Нуртаев: Добрый день, Qadam Academy, английский для инженеров.\n"
                                             "Клиент: Слушаю. Мы Арман Строй из Шымкента.\nАлибек Нуртаев: Сколько человек?\n"
                                             "Клиент: Пятеро.\n",
        "звонки.csv": "ID звонка;Дата;Говорящий;Текст\n"
                      "5534;16.09.2026 14:20:05;Оператор;Добрый день! Qadam Academy, корпоративный английский.\n"
                      '5534;16.09.2026 14:20:14;Абонент;"Мы ТОО ""Арман Строй Сервис"" из Караганды, нам уже предлагали."\n',
    }

    @classmethod
    def setUpClass(cls):
        cls.tmp = root = pathlib.Path(tempfile.mkdtemp())
        (root / "data" / "import").mkdir(parents=True); (root / "active").mkdir(); (root / "cabinet").mkdir()
        (root / "active" / "profile.json").write_text(json.dumps(cls.PROFILE, ensure_ascii=False), encoding="utf-8")
        for name, text in cls.FILES.items():
            (root / "data" / "import" / name).write_text(text, encoding="utf-8")
        (root / "blocks").mkdir(); (root / "scripts").mkdir()
        shutil.copy2(REPO / "blocks" / "config.template.js", root / "blocks" / "config.template.js")
        shutil.copy2(REPO / "scripts" / "build_data.py", root / "scripts" / "build_data.py")
        src = root / "data" / "import"
        imp.ROOT, imp.SRC = root, src
        imp.PARSED, imp.MAPPING, imp.DONE = src / "_parsed.json", src / "_mapping.json", src / "_done"
        imp.OWN, imp.CAB = root / "data" / "own", root / "cabinet"
        cls.out = io.StringIO(); stdout = sys.stdout; sys.stdout = cls.out
        try:
            imp.cmd_scan(None)
        finally:
            sys.stdout = stdout
        cls.mp = json.loads(imp.MAPPING.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def conv(self, key):
        return self.mp["conversations"][key]

    def test_manager_namesake_stays_client(self):
        # «Алибек» — как менеджер Алибек Нуртаев, но в чате, кроме него, только менеджер Динара
        self.assertEqual(self.conv("WhatsApp Chat - Алибек.txt")["speakers"]["Алибек"], "client")
        self.assertNotIn("«Алибек» →", self.out.getvalue())

    def test_build_stops_on_conversation_without_client(self):
        mp = json.loads(json.dumps(self.mp))
        mid = next(k for k, v in mp["managers"].items() if v == "Алибек Нуртаев")
        mp["conversations"]["WhatsApp Chat - Алибек.txt"]["speakers"]["Алибек"] = mid
        imp.MAPPING.write_text(json.dumps(mp, ensure_ascii=False), encoding="utf-8")
        out, stdout = io.StringIO(), sys.stdout; sys.stdout = out
        try:
            with self.assertRaises(SystemExit):
                imp.cmd_build(type("A", (), {"top_up": 0})())
        finally:
            sys.stdout = stdout
            imp.MAPPING.write_text(json.dumps(self.mp, ensure_ascii=False), encoding="utf-8")
        self.assertIn("WhatsApp Chat - Алибек.txt: в разговоре нет клиента", out.getvalue())

    def test_b2c_lead_is_the_whole_contact(self):
        for key, lead in (("Чат WhatsApp с Гульмира мама Санжара.txt", "Гульмира мама Санжара"),
                          ("Чат WhatsApp с Динара мама Амира.txt", "Динара мама Амира")):
            self.assertEqual(self.conv(key)["lead"], lead)      # тёзку менеджера не склеило с другой мамой
            self.assertEqual(self.conv(key)["lead_why"], "клиент из названия чата")

    def test_hint_same_company_in_latin_with_group(self):
        self.assertIn("«Madiyar Sunkar Media Group» — «Сункар Медиа» (то же название, общий клиент", self.out.getvalue())
        self.assertEqual(self.conv("2026-09-12_встреча_Сункар_Медиа.txt")["lead"], "Сункар Медиа")   # сама не склеивает

    def test_hint_one_name_chat_to_known_client(self):
        self.assertEqual(self.conv("WhatsApp Chat - Серик.txt")["lead"], "Серик")
        self.assertIn("«Серик» — «Каратау Агро» (клиент Серик Балтабаев)?", self.out.getvalue())

    def test_longer_company_name_is_not_a_mention(self):
        # «Арман Строй Сервис» из Караганды — не «Арман Строй» из Шымкента
        self.assertNotEqual(self.conv("звонки.csv")["lead"], "Арман Строй")


class TopUp(unittest.TestCase):
    """Догенерация не берёт ни имён, ни фамилий живых людей: ни из записей, ни из профиля,
    и добирает почти ровно до заказанного объёма."""

    def test_synthetic_people_are_not_real(self):
        root = pathlib.Path(tempfile.mkdtemp())
        try:
            (root / "active").mkdir(); (root / "data" / "import").mkdir(parents=True); (root / "scripts").mkdir()
            shutil.copy2(REPO / "scripts" / "generate_participant.py", root / "scripts" / "generate_participant.py")
            P = json.loads((REPO / "scripts" / "profile.example.json").read_text(encoding="utf-8"))
            P["managers"][0]["name"] = "Айжан Оспанова"          # в профиле настоящая команда
            (root / "active" / "profile.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
            (root / "data" / "import" / "_parsed.json").write_text(json.dumps(       # «мама Санжара»: Санжар тоже занят
                [{"speakers": {"Айжан Оспанова": 3, "Арман Касенов": 2, "Гульмира мама Санжара": 2}}],
                ensure_ascii=False), encoding="utf-8")
            imp.ROOT, imp.PARSED = root, root / "data" / "import" / "_parsed.json"
            base = {"profile": {}, "managers": [{"id": "m1", "name": "Айжан Оспанова"}], "calls": [], "chats": [], "leads": []}
            out = imp.top_up(base, 40)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        total = len(out["calls"]) + len(out["chats"])
        self.assertTrue(34 <= total <= 40, total)                 # до 40, недобор меньше одной сделки
        ids = {l["id"] for l in out["leads"]}
        self.assertTrue(all(x["lead_id"] in ids for x in out["calls"] + out["chats"]))
        real = {"айжан", "оспанова", "арман", "касенов", "санжар"}
        syn = [m["name"] for m in out["managers"] if m.get("synthetic")] + \
              [l.get("contact", "") for l in out["leads"] if l.get("synthetic")]
        self.assertTrue(syn)
        for name in syn:
            self.assertFalse(set(imp.norm(name.replace("· синтетика", "")).split()) & {imp.norm(w) for w in real}, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
