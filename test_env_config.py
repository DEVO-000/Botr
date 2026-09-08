# -*- coding: utf-8 -*-
"""test_env_config.py — v3.8: «бот не видит ИИ» из-за источников ключей.

Проверяет, что бот находит API-ключи ВО ВСЕХ документированных сценариях:
  1. bot_config.json рядом с main.py, запуск из ДРУГОЙ папки (панели хостинга,
     systemd, screen) — раньше ключи НЕ находились (относительный путь от CWD);
  2. ключи в .env рядом с main.py, запуск из папки бота — раньше .env вообще
     НЕ читался (инструкция обещала, код — нет);
  3. ключи в .env, запуск из другой папки;
  4. нет ни одного конфига — has_enabled_models() честно False;
  5. переменные окружения хостинга приоритетнее .env (setdefault);
  6. парсинг .env: кавычки, комментарии, пустые строки, BOM;
  7. bot_config.json в текущей папке запуска (fallback старых установок);
  8. gost_configs.json находится рядом с main.py при чужом CWD.

Каждый сценарий — отдельный subprocess с полной копией кода бота во
временной папке (конфиг читается при импорте main.py, в одном процессе
это нельзя проверить повторно).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.abspath(__file__))

RUNNER = '''# -*- coding: utf-8 -*-
import json, sys
import main  # импорт из папки сценария (sys.path[0] = папка runner.py)
print("RESULT:" + json.dumps({
    "has_enabled": main.has_enabled_models(),
    "deepseek": main.AI_MODELS["deepseek"]["api_key"],
    "openrouter": main.AI_MODELS["gemini_or"]["api_key"],
    "groq": main.AI_MODELS["groq"]["api_key"],
    "gost_cfgs": bool(main.GOST_CONFIGS),
}, ensure_ascii=False))
'''


def _copy_bot(dst: str) -> None:
    """Полная копия кода бота (без тестов) во временную папку сценария."""
    for f in os.listdir(SRC):
        if f.endswith(".py") and not f.startswith("test_"):
            shutil.copy(os.path.join(SRC, f), dst)
    for f in ("gost_configs.json", "bot_config.example.json"):
        p = os.path.join(SRC, f)
        if os.path.exists(p):
            shutil.copy(p, dst)


def _clean_env() -> dict:
    """Окружение без AI-ключей — чтобы сценарий был изолирован."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("BOT_TOKEN", "DEEPSEEK_KEY", "OPENROUTER_KEY", "GROQ_KEY")}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run(name: str, setup=None, env_extra=None, cwd=None):
    """Создаёт сценарий: tmp-папка с копией бота + setup(tmp) + subprocess."""
    tmp = tempfile.mkdtemp(prefix=f"envcfg_{name}_")
    _copy_bot(tmp)
    if setup:
        setup(tmp)
    env = _clean_env()
    if env_extra:
        env.update(env_extra)
    run_dir = cwd() if cwd else tmp
    runner = os.path.join(tmp, "__runner.py")
    with open(runner, "w", encoding="utf-8") as f:
        f.write(RUNNER)
    p = subprocess.run([sys.executable, runner], cwd=run_dir, env=env,
                       capture_output=True, text=True, timeout=180)
    result = None
    for line in (p.stdout or "").splitlines():
        if line.startswith("RESULT:"):
            result = json.loads(line[len("RESULT:"):])
            break
    return result, p


def write_bot_config(tmp, **kv) -> None:
    cfg = {"BOT_TOKEN": "123:TEST"}
    cfg.update(kv)
    with open(os.path.join(tmp, "bot_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def write_dotenv(tmp, text: str) -> None:
    with open(os.path.join(tmp, ".env"), "w", encoding="utf-8-sig") as f:
        f.write(text)


def other_cwd():
    """Свежая пустая папка как CWD запуска (не папка бота)."""
    return tempfile.mkdtemp(prefix="cwd_other_")


def collect_checks():
    checks = []

    # ── 1. bot_config.json рядом с main.py, CWD = другая папка ─────────────
    def s1(tmp):
        write_bot_config(tmp, DEEPSEEK_KEY="sk-case1")
    r, p = _run("case1", s1, cwd=other_cwd)
    checks.append(("bot_config.json рядом с main.py, запуск из другой папки",
                   bool(r and r["has_enabled"] and r["deepseek"] == "sk-case1"), p))

    # ── 2. ключи в .env рядом с main.py, запуск из папки бота ──────────────
    def s2(tmp):
        write_dotenv(tmp, "BOT_TOKEN=123:TEST\nDEEPSEEK_KEY=sk-case2\n")
    r, p = _run("case2", s2)
    checks.append(("ключи в .env, запуск из папки бота",
                   bool(r and r["deepseek"] == "sk-case2"), p))

    # ── 3. ключи в .env, запуск из другой папки ────────────────────────────
    r, p = _run("case3", s2, cwd=other_cwd)
    checks.append(("ключи в .env, запуск из другой папки",
                   bool(r and r["deepseek"] == "sk-case2"), p))

    # ── 4. конфигов нет вообще → честно False ──────────────────────────────
    r, p = _run("case4")
    checks.append(("нет конфигов → has_enabled_models() == False",
                   bool(r and not r["has_enabled"]), p))

    # ── 5. env хостинга приоритетнее .env (setdefault не перезаписывает) ───
    r, p = _run("case5", s2, env_extra={"DEEPSEEK_KEY": "sk-hosting-wins"})
    checks.append(("переменные окружения хостинга приоритетнее .env",
                   bool(r and r["deepseek"] == "sk-hosting-wins"), p))

    # ── 6. парсинг .env: кавычки, комментарии, пустые строки, BOM ──────────
    def s6(tmp):
        write_dotenv(tmp,
                     "# комментарий целиком\n"
                     "\n"
                     'OPENROUTER_KEY="sk-or-quoted"  # хвостовой комментарий\n'
                     "GROQ_KEY='gsk-single'\n"
                     "DEEPSEEK_KEY=sk-plain # коммент\n"
                     "СТРОКА_БЕЗ_РАВНО_ПРОПУЩЕНА\n")
    r, p = _run("case6", s6)
    checks.append(("парсинг .env: кавычки/комментарии/пустые строки/BOM",
                   bool(r and r["deepseek"] == "sk-plain"
                        and r["openrouter"] == "sk-or-quoted"
                        and r["groq"] == "gsk-single"), p))

    # ── 7. bot_config.json в текущей папке запуска (fallback старых) ───────
    def s7(tmp):
        pass  # конфиг кладём в CWD, а не рядом с main.py
    def cwd7():
        d = other_cwd()
        write_bot_config(d, DEEPSEEK_KEY="sk-legacy-cwd")
        return d
    r, p = _run("case7", s7, cwd=cwd7)
    checks.append(("bot_config.json в CWD (fallback старых установок)",
                   bool(r and r["deepseek"] == "sk-legacy-cwd"), p))

    # ── 8. gost_configs.json рядом с main.py находится при чужом CWD ───────
    r, p = _run("case8", None, cwd=other_cwd)
    checks.append(("gost_configs.json найден рядом с main.py при чужом CWD",
                   bool(r and r["gost_cfgs"]), p))

    return checks


def main() -> int:
    checks = collect_checks()
    fails = 0
    print("=" * 70)
    for name, ok, proc in checks:
        mark = "✅ OK  " if ok else "❌ FAIL"
        print(f"{mark}  {name}")
        if not ok:
            fails += 1
            tail = (proc.stderr or proc.stdout or "(пустой вывод)")[-600:]
            print(f"        хвост вывода:\n{tail}")
    print("=" * 70)
    print(f"TOTAL: {len(checks) - fails}/{len(checks)} OK, FAILS: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
