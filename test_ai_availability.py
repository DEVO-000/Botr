# -*- coding: utf-8 -*-
"""test_ai_availability.py — регрессионные тесты v3.7 «бот не видит ИИ».

Проверяет, что ИИ-модели больше НЕ «умирают навсегда» из-за:
  • самонакрутки счётчика перегрузки (таймауты/пропуски без реальных запросов);
  • вечного _fatal после одной ошибки 401/402/403;
  • пустого меню моделей (модели с ключом не исчезают из kb_models);
  • залипшего статуса LIMIT в меню.

Все тесты ОФЛАЙНОВЫЕ: HTTP полностью замокан. Запуск: python test_ai_availability.py
"""

import asyncio
import os
import sys
import time

os.environ.setdefault("BOT_TOKEN", "123:TEST")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  OK  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL {name} {extra}")


def _fresh_model(key: str = "deepseek") -> dict:
    """Чистая копия модели для изоляции тестов от глобального состояния."""
    import copy
    info = copy.deepcopy(main.AI_MODELS[key])
    info["api_key"] = "sk-test-key"
    info["_fatal"] = False
    info["_fatal_ts"] = 0
    info["_cooldown_until"] = 0
    info["_status_ts"] = 0
    info["status"] = main.ModelStatus.UNKNOWN
    return info


def _reset_overload_state() -> None:
    main._api_overload_state.clear()


# ────────────────────────────────────────────────────────────────
# 1. Окно перегрузки: честный отсчёт и самовосстановление
# ────────────────────────────────────────────────────────────────
def test_overload_window() -> None:
    print("\n[1] Окно перегрузки без самонакрутки")
    _reset_overload_state()
    key = "test_model"

    check("до ошибок модель не перегружена", not main.is_api_overloaded(key))

    main.increment_overload(key)
    main.increment_overload(key)
    check("2 ошибки < порога", not main.is_api_overloaded(key))

    main.increment_overload(key)
    check("3 реальные ошибки → перегрузка", main.is_api_overloaded(key))

    # Сдвигаем окно в прошлое БОЛЬШЕ порога окна — счётчик должен погаснуть сам
    ws, cnt = main._api_overload_state[key]
    main._api_overload_state[key] = (ws - (main._OVERLOAD_WINDOW_SEC + 10), cnt)
    check("после окна перегрузка гаснет САМА", not main.is_api_overloaded(key))

    # reset_overload после успеха
    _reset_overload_state()
    main.increment_overload(key)
    main.increment_overload(key)
    main.increment_overload(key)
    main.reset_overload(key)
    check("успех сбрасывает счётчик", not main.is_api_overloaded(key))


# ────────────────────────────────────────────────────────────────
# 2. Cooldown: 429 ставит паузу, в паузу запросов НЕ выполняется
# ────────────────────────────────────────────────────────────────
class _FakeResp:
    def __init__(self, status: int, headers: dict | None = None, text: str = "{}"):
        self.status = status
        self.headers = headers or {}
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """Подменяет aiohttp.ClientSession: считает реальные HTTP-вызовы."""

    calls = 0
    response: "_FakeResp | None" = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, *a, **k):
        _FakeSession.calls += 1
        return _FakeSession.response


def test_cooldown_no_http() -> None:
    print("\n[2] Cooldown после 429: без HTTP и без самонакрутки")
    _reset_overload_state()
    info = _fresh_model()

    _FakeSession.calls = 0
    _FakeSession.response = _FakeResp(429, {"Retry-After": "120"})
    real_session = main.aiohttp.ClientSession
    main.aiohttp.ClientSession = _FakeSession
    try:
        # Первый вызов реально стучится и получает 429 → cooldown 120 c
        text1 = asyncio.run(main.chat_with_model(info, [{"role": "user", "content": "тест"}]))
        check("429 → пустой ответ", text1 == "")
        check("1 реальный HTTP-запрос был", _FakeSession.calls == 1,
              f"calls={_FakeSession.calls}")
        check("cooldown установлен ~120 c", 100 <= main.model_cooldown_left(info) <= 120)
        check("429 учтён в счётчике перегрузки", main._api_overload_state.get("deepseek", (0, 0))[1] == 1)

        # Повторный вызов в cooldown: НЕ должен выполнить HTTP и НЕ должен
        # накрутить счётчик (это и была «смертная спираль»)
        calls_before = _FakeSession.calls
        cnt_before = main._api_overload_state.get("deepseek", (0, 0))[1]
        text2 = asyncio.run(main.chat_with_model(info, [{"role": "user", "content": "тест"}]))
        check("в cooldown ответ пустой", text2 == "")
        check("в cooldown HTTP НЕ выполняется", _FakeSession.calls == calls_before,
              f"calls: {calls_before} → {_FakeSession.calls}")
        cnt_after = main._api_overload_state.get("deepseek", (0, 0))[1]
        check("в cooldown счётчик НЕ растёт", cnt_after == cnt_before,
              f"cnt: {cnt_before} → {cnt_after}")

        # call_openai_compat тоже уважает cooldown напрямую
        text3 = asyncio.run(main.call_openai_compat(info, [{"role": "user", "content": "тест"}]))
        check("call_openai_compat в cooldown → пусто", text3 == "")
        check("call_openai_compat не бьёт HTTP в cooldown", _FakeSession.calls == calls_before)
    finally:
        main.aiohttp.ClientSession = real_session


def test_retry_after_parsing() -> None:
    print("\n[3] Парсинг Retry-After")
    check("число '120'", main._parse_retry_after("120") == 120.0)
    check("мусор → дефолт", main._parse_retry_after("abc") == float(main.MODEL_COOLDOWN_DEFAULT_SEC))
    check("пусто → дефолт", main._parse_retry_after(None) == float(main.MODEL_COOLDOWN_DEFAULT_SEC))
    check("0 → минимум 5 с", main._parse_retry_after("0") == 5.0)


# ────────────────────────────────────────────────────────────────
# 4. _fatal: ставится по 401/402/403 и АВТОМАТИЧЕСКИ снимается
# ────────────────────────────────────────────────────────────────
def test_fatal_auto_recovery() -> None:
    print("\n[4] _fatal с авто-восстановлением")
    _reset_overload_state()
    info = _fresh_model()

    _FakeSession.calls = 0
    _FakeSession.response = _FakeResp(402, {}, '{"error": "insufficient credits"}')
    real_session = main.aiohttp.ClientSession
    main.aiohttp.ClientSession = _FakeSession
    try:
        text = asyncio.run(main.call_openai_compat(info, [{"role": "user", "content": "тест"}]))
        check("402 → пустой ответ", text == "")
        check("402 → _fatal активен", info.get("_fatal") is True)
        check("fatal_active() подтверждает", main.model_fatal_active(info))

        # Пока _fatal активен — HTTP не выполняется
        calls_before = _FakeSession.calls
        asyncio.run(main.chat_with_model(info, [{"role": "user", "content": "тест"}]))
        check("в _fatal HTTP не выполняется", _FakeSession.calls == calls_before)

        # «Прокручиваем время» на срок больше окна восстановления
        info["_fatal_ts"] = time.time() - (main.MODEL_FATAL_RECOVERY_SEC + 5)
        check("после таймаута _fatal снят САМ", not main.model_fatal_active(info))
        check("модель снова пробуем (cooldown нет)", not main.model_in_cooldown(info))
    finally:
        main.aiohttp.ClientSession = real_session


# ────────────────────────────────────────────────────────────────
# 5. fallback_chain: никогда не пустая; cooldown — в конец
# ────────────────────────────────────────────────────────────────
def test_fallback_chain_never_empty() -> None:
    print("\n[5] fallback_chain: живучесть цепочки")
    _reset_overload_state()
    saved = {k: dict(v) for k, v in main.AI_MODELS.items()}
    try:
        for k, v in main.AI_MODELS.items():
            v["api_key"] = f"key-{k}"
            v["_fatal"] = False
            v["_fatal_ts"] = 0
            v["_cooldown_until"] = 0

        # Все модели живы: primary первый, дубликатов нет
        chain = main.fallback_chain("deepseek")
        check("живая цепочка начинается с primary", chain and chain[0] == "deepseek")
        check("цепочка без дубликатов", len(chain) == len(set(chain)))

        # Все модели в _fatal: цепочка ВСЁ РАВНО не пустая
        for v in main.AI_MODELS.values():
            v["_fatal"] = True
            v["_fatal_ts"] = time.time()
        chain_dead = main.fallback_chain("deepseek")
        check("при всех _fatal цепочка НЕ пустая", len(chain_dead) >= 1,
              f"chain={chain_dead}")

        # Cooldown-модели уходят в конец, но остаются в цепочке
        for v in main.AI_MODELS.values():
            v["_fatal"] = False
        main.AI_MODELS["deepseek"]["_cooldown_until"] = time.time() + 300
        main.AI_MODELS["groq"]["_cooldown_until"] = time.time() + 300
        chain_cool = main.fallback_chain("deepseek")
        check("cooldown-модели в конце, но В цепочке",
              "deepseek" in chain_cool and "groq" in chain_cool
              and chain_cool.index("deepseek") > chain_cool.index("deepseek_r1"),
              f"chain={chain_cool}")
    finally:
        main.AI_MODELS.clear()
        main.AI_MODELS.update(saved)


# ────────────────────────────────────────────────────────────────
# 6. Меню моделей: модель с ключом НЕ исчезает; пустое меню только без ключей
# ────────────────────────────────────────────────────────────────
def test_menu_never_hides_models() -> None:
    print("\n[6] kb_models: модель с ключом всегда видна")
    saved = {k: dict(v) for k, v in main.AI_MODELS.items()}
    try:
        for k, v in main.AI_MODELS.items():
            v["api_key"] = f"key-{k}"
            v["_fatal"] = False
            v["_fatal_ts"] = 0
            v["_cooldown_until"] = 0
            v["_status_ts"] = 0
            v["status"] = main.ModelStatus.UNKNOWN

        n_ok = len(main.kb_models().inline_keyboard)
        check("4 модели с ключами → 4 кнопки", n_ok == 4, f"got {n_ok}")

        # Все модели «умерли»: кнопки ВСЁ РАВНО на месте, с честной пометкой
        for v in main.AI_MODELS.values():
            v["_fatal"] = True
            v["_fatal_ts"] = time.time()
        n_dead = len(main.kb_models().inline_keyboard)
        check("даже при всех _fatal меню НЕ пустое", n_dead == 4, f"got {n_dead}")
        label = main.model_menu_status_label(main.AI_MODELS["deepseek"])
        check("помечтка _fatal честная (🔴 с ETA)", "🔴" in label and "авто-повтор" in label, label)

        # Залипший LIMIT старше 10 минут → снова ❓ (модель можно пробовать)
        for v in main.AI_MODELS.values():
            v["_fatal"] = False
        main.AI_MODELS["deepseek"]["status"] = main.ModelStatus.LIMIT
        main.AI_MODELS["deepseek"]["_status_ts"] = time.time() - 3600
        label_stale = main.model_menu_status_label(main.AI_MODELS["deepseek"])
        check("залипший LIMIT гаснет в ❓", label_stale == main.ModelStatus.UNKNOWN, label_stale)

        # Без единого ключа: model_menu_message даёт честный текст, а не пустую клавиатуру
        for v in main.AI_MODELS.values():
            v["api_key"] = ""
        txt, markup = main.model_menu_message("заглушка")
        check("без ключей: честный текст вместо немого меню",
              "не настроены" in txt and "API-ключ" in txt)
        check("без ключей: навигация сохранена",
              any(b.callback_data == "back_flow"
                  for row in markup.inline_keyboard for b in row))
    finally:
        main.AI_MODELS.clear()
        main.AI_MODELS.update(saved)


# ────────────────────────────────────────────────────────────────
# 7. Успешный ответ снимает перегрузку и возвращает статус AVAILABLE
# ────────────────────────────────────────────────────────────────
def test_success_recovers() -> None:
    print("\n[7] Успех восстанавливает модель")
    _reset_overload_state()
    info = _fresh_model()
    _FakeSession.calls = 0
    _FakeSession.response = _FakeResp(
        200, {},
        '{"choices": [{"message": {"content": "' + "Успешный академический ответ модели. " * 5 + '", "role": "assistant"}, "finish_reason": "stop"}]}'
    )
    real_session = main.aiohttp.ClientSession
    main.aiohttp.ClientSession = _FakeSession
    try:
        # Сперва «перегружаем» модель
        main.increment_overload("deepseek")
        main.increment_overload("deepseek")
        main.increment_overload("deepseek")
        check("модель перегружена", main.is_api_overloaded("deepseek"))

        text = asyncio.run(main.chat_with_model(info, [{"role": "user", "content": "тест"}]))
        check("успешный ответ возвращён", len(text.strip()) > 100)
        check("успех сбросил перегрузку", not main.is_api_overloaded("deepseek"))

        # 200 ответ НЕ должен ставить cooldown/_fatal
        check("успех не ставит _fatal", not main.model_fatal_active(info))
        check("успех не ставит cooldown", not main.model_in_cooldown(info))
    finally:
        main.aiohttp.ClientSession = real_session
        _reset_overload_state()


# ────────────────────────────────────────────────────────────────
# 8. Таймаут не накручивает счётчик перегрузки
# ────────────────────────────────────────────────────────────────
def test_timeout_not_counted() -> None:
    print("\n[8] Таймаут ≠ перегрузка")
    _reset_overload_state()
    info = _fresh_model()

    class _TimeoutSession:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        def post(self, *a, **k):
            raise asyncio.TimeoutError()

    real_session = main.aiohttp.ClientSession
    main.aiohttp.ClientSession = _TimeoutSession
    try:
        for _ in range(5):
            text = asyncio.run(main.chat_with_model(info, [{"role": "user", "content": "тест"}]))
            check_reply = (text == "")
        check("таймаут → пустой ответ", check_reply)
        check("5 таймаутов НЕ сделали модель перегруженной",
              not main.is_api_overloaded("deepseek"),
              f"state={main._api_overload_state.get('deepseek')}")
        check("таймауты не ставят cooldown", not main.model_in_cooldown(info))
    finally:
        main.aiohttp.ClientSession = real_session
        _reset_overload_state()


if __name__ == "__main__":
    print("=" * 64)
    print("ТЕСТ: доступность ИИ-моделей (v3.7 «бот не видит ИИ»)")
    print("=" * 64)

    test_overload_window()
    test_cooldown_no_http()
    test_retry_after_parsing()
    test_fatal_auto_recovery()
    test_fallback_chain_never_empty()
    test_menu_never_hides_models()
    test_success_recovers()
    test_timeout_not_counted()

    print("\n" + "=" * 64)
    print(f"ИТОГО: OK={len(PASS)}  FAIL={len(FAIL)}")
    if FAIL:
        print("Провалены:")
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ ✅")
