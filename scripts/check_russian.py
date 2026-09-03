"""Остаток Д2: проверка качества русского на живых записях.

Использование (на машине с доступом к AssemblyAI — ПК/Коренёво):
    export ASSEMBLYAI_API_KEY=...
    python scripts/check_russian.py путь/к/записи.mp3 [путь/к/эталону.txt]

Печатает: длительность, число реплик, транскрипт (можно сравнить с эталоном).
Эталон (файл .txt) — ручная расшифровка первых 2 минут: тогда выводится
грубая оценка WER (по словам) для быстрой проверки «точность >= 90%».
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from secretary.config import get_settings
from secretary.stt.base import get_provider


def wer_estimate(reference: str, hypothesis: str) -> float:
    """Грубый WER по словам (без выравнивания — для быстрой прикидки)."""
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    if not ref:
        return 1.0
    # мешок слов: доля слов эталона, не встретившихся в гипотезе
    from collections import Counter

    hyp_counter = Counter(hyp)
    missing = sum(max(0, ref_counter - hyp_counter[word]) for word, ref_counter in Counter(ref).items())
    return missing / len(ref)


async def main(audio: str, reference: str | None) -> None:
    settings = get_settings()
    audio_bytes = Path(audio).read_bytes()
    print(f"Аудио: {audio} · {len(audio_bytes) / 1_048_576:.1f} МБ · провайдер={settings.stt_provider}")
    provider = get_provider(settings)
    result = await provider.transcribe_file(audio_bytes, language=settings.language_code)
    print(f"Длительность: {result.audio_duration_sec:.0f} с · реплик спикеров: {len(result.utterances)}")
    print("--- Транскрипт ---")
    print(result.to_dialogue()[:4000])
    if reference:
        ref_text = Path(reference).read_text(encoding="utf-8")
        wer = wer_estimate(ref_text, result.text)
        acc = max(0.0, 1.0 - wer)
        verdict = "OK (>=90%)" if acc >= 0.90 else "НИЖЕ 90% — пересмотреть провайдера/модель"
        print(f"--- Оценка ---\nТочность (1 - WER, грубо): {acc:.1%} → {verdict}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))