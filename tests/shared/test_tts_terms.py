# Copyright 2026 GrillKit Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the question-voice terms dictionary."""

import pytest

from app.shared.tts_terms import apply_term_substitutions


class TestApplyTermSubstitutions:
    """Tests for apply_term_substitutions."""

    def test_expands_latin_terms_for_russian(self):
        """Russian locale replaces known Latin terms with Cyrillic."""
        prepared = apply_term_substitutions(
            "Как работает Kubernetes и CI/CD в Python?",
            "ru",
        )
        assert prepared == "Как работает кубернетес и си ай си ди в пайтон?"

    def test_longest_term_wins_over_prefix(self):
        """PostgreSQL is one dictionary word, not SQL with a prefix."""
        prepared = apply_term_substitutions(
            "Чем PostgreSQL отличается от SQL?",
            "ru",
        )
        assert prepared == "Чем постгрес отличается от эс кью эл?"

    def test_word_boundaries_protect_embedded_words(self):
        """Replacements do not touch longer words containing the term."""
        prepared = apply_term_substitutions(
            "frozenset можно использовать как ключ, а set — нет.",
            "ru",
        )
        assert prepared == "фрозенсет можно использовать как ключ, а сет — нет."

    def test_replacements_are_case_insensitive(self):
        """Lowercase and uppercase spellings are expanded alike."""
        prepared = apply_term_substitutions(
            "docker запускает DAG из Airflow.",
            "ru",
        )
        assert prepared == "докер запускает даг из эйрфлоу."

    def test_event_loop_is_spoken_word_by_word(self):
        """Each Latin word of a phrase is looked up in the dictionary."""
        prepared = apply_term_substitutions(
            "Что такое event loop в asyncio?",
            "ru",
        )
        assert prepared == "Что такое ивент луп в асинк ай о?"

    def test_unknown_abbreviation_is_spelled(self):
        """Short uppercase words missing from the dictionary go letter by letter."""
        assert apply_term_substitutions("Что такое XYZ?", "ru") == (
            "Что такое экс уай зед?"
        )

    def test_unknown_word_is_transliterated(self):
        """Unknown English words fall back to simple transliteration."""
        assert apply_term_substitutions("Что делает blob?", "ru") == (
            "Что делает блоб?"
        )

    def test_camel_case_is_split(self):
        """CamelCase identifiers are spoken part by part."""
        assert apply_term_substitutions("Что такое PodDisruptionBudget?", "ru") == (
            "Что такое под дисрупшн бюджет?"
        )

    def test_no_latin_letters_remain(self):
        """Silero drops Latin letters, so none may reach the engine."""
        prepared = apply_term_substitutions(
            "Сравните FastAPI, gRPC, S3 и ext4 в CI/CD на k8s через HTTP/2.",
            "ru",
        )
        assert not any("a" <= ch.lower() <= "z" for ch in prepared)
        assert not any(ch.isdigit() for ch in prepared)

    def test_english_locale_is_unchanged(self):
        """English text keeps Latin terms for the Latin-script voice."""
        text = "How does Kubernetes handle CI/CD pipelines?"
        assert apply_term_substitutions(text, "en") == text

    def test_unknown_locale_is_unchanged(self):
        """Unknown locales are a no-op instead of an error."""
        text = "Что такое Kubernetes?"
        assert apply_term_substitutions(text, "xx") == text

    def test_cyrillic_only_text_is_unchanged(self):
        """Pure Cyrillic text passes through untouched."""
        text = "Что такое оркестрация контейнеров?"
        assert apply_term_substitutions(text, "ru") == text


class TestRussianNumbers:
    """Digits are spelled out for Russian (Silero drops them otherwise)."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Назовите 3 причины.", "Назовите три причины."),
            ("Приведите 25 примеров.", "Приведите двадцать пять примеров."),
            ("Порт 0", "Порт ноль"),
            ("Ровно 1000", "Ровно одна тысяча"),
            ("Ровно 2000", "Ровно две тысячи"),
            ("12 345", "двенадцать триста сорок пять"),
            ("21000 строк", "двадцать одна тысяча строк"),
            ("1500000", "один миллион пятьсот тысяч"),
            ("Версия 3.12", "Версия три точка двенадцать"),
            ("Код 007", "Код ноль ноль семь"),
        ],
    )
    def test_spells_numbers(self, raw, expected):
        """Integers, scales, decimals and leading zeros read as words."""
        assert apply_term_substitutions(raw, "ru") == expected

    def test_separates_digits_glued_to_letters(self):
        """Digits after a term are spaced so words do not merge."""
        assert apply_term_substitutions("HTTP/2", "ru") == "эйч ти ти пи два"
        assert apply_term_substitutions("v5 модели", "ru") == "ви пять модели"

    def test_other_locales_keep_digits(self):
        """Latin-script voices read digits natively."""
        assert apply_term_substitutions("Name 3 reasons.", "en") == "Name 3 reasons."
