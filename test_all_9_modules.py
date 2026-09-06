# -*- coding: utf-8 -*-
"""Comprehensive unit and integration test for all 9 modules."""

import asyncio

from rag_engine import chunk_text, find_relevant_chunks, format_rag_context, Chunk
from fact_checker import validate_facts_in_text as fc_validate, auto_cite_facts
from style_variator import mix_styles
from plagiarism_checker import PlagiarismChecker

from rag_full import FullTextRAG
from fact_checker_real import RealFactChecker
from plagiarism_detector import PlagiarismDetector
from quality_gate_ultimate import UltimateQualityGate

from main import enhance_with_rag_and_facts


async def mock_chat_fn(model_key, messages, max_tokens):
    return "Сгенерированный тект с ответом на промпт.", model_key


async def test_all_modules():
    print("Testing Module 1 (rag_engine)...")
    chunks = chunk_text("слово " * 500)
    assert len(chunks) > 0

    print("Testing Module 2 (fact_checker)...")
    facts = await fc_validate("В 2024 году объем производства вырос на 20%.", "тема")
    assert len(facts) >= 1

    print("Testing Module 3 (style_variator)...")
    mixed = mix_styles("Введение к исследованию. Обзор предметной области. Заключение работы.")
    assert ".." not in mixed

    print("Testing Module 4 (plagiarism_checker)...")
    pc = PlagiarismChecker()
    score = await pc.check_uniqueness("Уникальный текст для тестового прогона системных функций.")
    assert score >= 0

    print("Testing Module 5 (rag_full)...")
    async with FullTextRAG() as rag:
        gen_text = await rag.generate_with_sources("Тема", "10.1000/182", "mock", mock_chat_fn)
        assert isinstance(gen_text, str)

    print("Testing Module 6 (fact_checker_real)...")
    async with RealFactChecker() as rfc:
        verified, reason = await rfc.verify_fact("В 2023 году был принят закон.")
        assert isinstance(verified, bool)

    print("Testing Module 7 (plagiarism_detector)...")
    pd = PlagiarismDetector()
    matches = pd.detect_plagiarism("в современных условиях подходы отличаются.")
    assert len(matches) > 0

    print("Testing Module 8 (quality_gate_ultimate)...")
    gate = UltimateQualityGate()
    parts = {
        "intro": "В современном мире это имеет важное значение.",
        "ch1": "Первый раздел работы.",
    }
    fixed_parts, fixes = await gate.check_and_fix(parts, "Тема", "Предмет", "mock", mock_chat_fn, max_attempts=1)
    assert isinstance(fixed_parts, dict)

    print("Testing Module 9 (enhance_with_rag_and_facts integration)...")
    enhanced = await enhance_with_rag_and_facts(parts, "Тема", "10.1000/182", "mock")
    assert "intro" in enhanced

    print("ALL 9 MODULE TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_all_modules())
