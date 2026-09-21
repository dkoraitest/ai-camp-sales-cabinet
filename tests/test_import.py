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
        # полный архив Telegram в папке экспорта: рабочий чат, «Мама», «Избранное»
        (src / "ChatExport_2026-09-20").mkdir()
        (src / "ChatExport_2026-09-20" / "result.json").write_text(json.dumps({"chats": {"list": [
            {"type": "saved_messages", "messages": [{"type": "message", "from": "Асель Ким", "text": "пароль от wifi"}]},
            {"name": "Мама", "type": "personal_chat", "messages": [
                {"type": "message", "date": "2026-09-20T09:00:00", "from": "Мама", "text": "Ты во сколько сегодня?"},
                {"type": "message", "date": "2026-09-20T09:01:00", "from": "Асель Ким", "text": "В 8"}]},
            {"name": "Руслан Каспий Трейд", "type": "personal_chat", "messages": [
                {"type": "message", "date": "2026-09-19T14:00:00", "from": "Асель Ким", "text": "Руслан, отправляю КП, как обсуждали."},
                {"type": "message", "date": "2026-09-19T14:10:00", "from": "Руслан Ибраев", "text": "Получил. Дорого."}]}]}},
            ensure_ascii=False), encoding="utf-8")
        for name in ("ROOT", "SRC", "PARSED", "MAPPING", "DONE", "OWN", "CAB"):
            pass
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
