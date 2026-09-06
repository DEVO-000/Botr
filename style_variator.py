# -*- coding: utf-8 -*-
"""style_variator — варьирование длины предложений для естественности.

Вместо вставки маркеров стилей (которые humanizer удаляет),
варьирует ритм текста через разбиение/объединение предложений.
"""

import random
import re


def vary_sentence_length(text: str) -> str:
    """
    Варьирует длину предложений для естественного ритма.
    
    - Разбивает длинные предложения (>120 символов) по ; и :
    - Объединяет короткие предложения (<40 символов) в группы по 2-3
    - Сохраняет все ссылки и факты
    """
    if not text or len(text) < 200:
        return text
    
    # Защищаем ссылки от разбиения
    citations = re.findall(r'\[\d+,\s*с\.\s*\d+\]', text)
    placeholders = {}
    for i, cit in enumerate(citations):
        placeholder = f"__CIT{i}__"
        placeholders[placeholder] = cit
        text = text.replace(cit, placeholder)
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) < 4:
        # Восстанавливаем ссылки
        for placeholder, cit in placeholders.items():
            text = text.replace(placeholder, cit)
        return text
    
    result = []
    i = 0
    while i < len(sentences):
        # Случайно объединяем 2-3 коротких предложения
        if len(sentences[i]) < 40 and i + 1 < len(sentences) and random.random() < 0.3:
            combined = sentences[i].strip()
            j = i + 1
            while j < len(sentences) and len(sentences[j]) < 40 and j - i < 3:
                # Второе и третье предложения начинаем со строчной
                next_sent = sentences[j].strip()
                if next_sent and next_sent[0].isupper():
                    next_sent = next_sent[0].lower() + next_sent[1:]
                combined += " " + next_sent
                j += 1
            # Добавляем точку в конце, если её нет
            if combined and combined[-1] not in '.!?':
                combined += '.'
            result.append(combined)
            i = j
        # Случайно разбиваем длинное предложение
        elif len(sentences[i]) > 120 and random.random() < 0.4:
            parts = re.split(r'[;:]', sentences[i])
            if len(parts) >= 2:
                for part in parts:
                    part = part.strip()
                    if part:
                        if part and part[0].islower():
                            part = part[0].upper() + part[1:]
                        if part[-1] not in '.!?':
                            part += '.'
                        result.append(part)
                i += 1
                continue
            result.append(sentences[i])
            i += 1
        else:
            result.append(sentences[i])
            i += 1
    
    # Восстанавливаем ссылки
    final_text = " ".join(result)
    for placeholder, cit in placeholders.items():
        final_text = final_text.replace(placeholder, cit)
    
    return final_text


def mix_styles(text: str) -> str:
    """
    Устаревшая функция. Используйте vary_sentence_length().
    
    Предупреждение об устаревании для обратной совместимости.
    """
    import warnings
    warnings.warn(
        "mix_styles() устарела. Используйте vary_sentence_length() для варьирования ритма.",
        DeprecationWarning,
        stacklevel=2
    )
    return vary_sentence_length(text)
