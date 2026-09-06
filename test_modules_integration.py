# -*- coding: utf-8 -*-
"""Unit and integration tests for new RAG, fact checker, style variator, plagiarism checker modules."""

import asyncio

from rag_engine import chunk_text, find_relevant_chunks, format_rag_context, Chunk
from fact_checker import validate_facts_in_text, auto_cite_facts
from style_variator import mix_styles
from plagiarism_checker import PlagiarismChecker
from main import enhance_with_rag_and_facts


def test_rag_engine_chunking():
    text = " " .join([f"word{i}" for i in range(1500)])
    chunks = chunk_text(text, chunk_size=1000, overlap=200)
    assert len(chunks) > 1

    relevant = find_relevant_chunks("word10 word20 word30", text, top_k=2)
    assert isinstance(relevant, list)

    formatted = format_rag_context([Chunk(text="sample chunk", source="10.1000/182", page=1)])
    assert "[ИЗ НАУЧНЫХ ИСТОЧНИКОВ:]" in formatted
    assert "sample chunk" in formatted


async def test_fact_checker():
    text = "В 2023 году объём производства вырос на 15% во всех регионах страны."
    facts = await validate_facts_in_text(text, topic="производство")
    assert len(facts) > 0
    assert "sentence" in facts[0]

    # ФИКС (v3.4, честная политика): auto_cite_facts больше НЕ выдумывает
    # ссылки вида «[1, с. 15]» из воздуха. Текст без ссылок обязан остаться
    # без ссылок — преподаватель проверяет страницы первым делом.
    lit = "1. Иванов И.И. Статья // Журнал. 2023. DOI: 10.1000/182"
    cited = await auto_cite_facts("mock_key", text, lit)
    assert cited == text, "auto_cite_facts не должен вставлять выдуманные ссылки"
    assert "[1, с." not in cited


def test_style_variator():
    original = "Данное исследование посвященное актуальным вопросам развития экономики. Было рассмотрено несколько гипотез. Результаты демонстрируют положительную динамику."
    mixed = mix_styles(original)
    assert isinstance(mixed, str)
    assert len(mixed) > 0


async def test_plagiarism_checker():
    checker = PlagiarismChecker()
    sample_text = "Это достаточно длинный текст для проверки работы модуля уникальности в системе. " * 5
    score = await checker.check_uniqueness(sample_text)
    assert 0 <= score <= 100

    text, ensured_score = await checker.ensure_uniqueness(sample_text, target=70.0)
    assert isinstance(text, str)


async def test_enhance_integration():
    parts = {
        "intro": "В 2022 году показатель составил 50% без ссылок.",
        "ch1": "Теоретические основы предмета.",
        "literature": "1. Test DOI 10.1000/123456",
    }
    enhanced = await enhance_with_rag_and_facts(parts, "Тестовая тема", parts["literature"], "deepseek_r1")
    assert "intro" in enhanced
    assert "ch1" in enhanced


if __name__ == "__main__":
    print("Running tests...")
    test_rag_engine_chunking()
    asyncio.run(test_fact_checker())
    test_style_variator()
    asyncio.run(test_plagiarism_checker())
    asyncio.run(test_enhance_integration())
    print("All tests passed successfully!")
