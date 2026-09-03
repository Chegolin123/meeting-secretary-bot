"""Роутер саммари по vault (v1.0): DeepSeek решает, куда писать; не уверен — ask.

Правило: НИКОГДА не угадывать. confidence < 0.75 или конфликт → mode="ask",
мост кладёт заметку во «Входящие/Созвоны» и создаёт файл-вопрос владельцу.
"""

from __future__ import annotations

import dataclasses
import json
import re


@dataclasses.dataclass
class RouteDecision:
    mode: str  # append | new | ask
    note_name: str = ''  # имя заметки (для new/append)
    folder: str = ''  # для new: относительная папка
    target_path: str = ''  # для append: путь существующей заметки (относит. vault)
    confidence: float = 0.0
    reason: str = ''

    @property
    def confident(self) -> bool:
        return self.mode != 'ask' and self.confidence >= 0.75


def build_route_prompt(summary: dict, catalog: list[dict[str, str]], order_id: int) -> str:
    """Промпт для DeepSeek: дал саммари и каталог vault → указал цель или ask."""
    catalog_lines = '\n'.join(f"- {c['path']}  ({c['name']})" for c in catalog[:80]) or '- (каталог пуст)'
    payload = json.dumps({'summary': summary, 'order_id': order_id}, ensure_ascii=False)
    return (
        'Ты — роутер заметок в Obsidian vault. По саммари созвона и каталогу vault определи, '
        'куда сохранить заметку о созвоне. Каталог = список существующих заметок (путь + имя).\n\n'
        'ПРАВИЛА:\n'
        "1. Если саммари явно относится к существующей заметке (проект/тема совпадают) — выбери её: "
        'mode="append", target_path=<путь из каталога>.\n'
        "2. Если темы явно относятся к области vault, где нет подходящей заметки — предложи новую: "
        'mode="new", folder=<существующая папка верхнего уровня>, note_name=<краткое имя>.\n'
        "3. Если не уверен, тема общая/личная или несколько равнозначных кандидатов — НЕ додумывай: "
        'mode="ask", причину в reason.\n'
        '4. confidence — от 0 до 1 (насколько уверен в выборе).\n\n'
        'Ответь ТОЛЬКО валидным JSON:\n'
        '{"mode": "append|new|ask", "note_name": "", "folder": "", "target_path": "", '
        '"confidence": 0.0, "reason": "кратко почему"}\n\n'
        '=== КАТАЛОГ VAULT ===\n'
        f'{catalog_lines}\n\n=== САММАРИ СОЗВОНА ===\n{payload}'
    )


def parse_route_answer(content: str) -> RouteDecision:
    """Парсинг ответа роутера. Не-JSON или странная форма → ask (не додумываем)."""
    text = content.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find('{'), text.rfind('}')
        if start == -1 or end == -1:
            return RouteDecision(mode='ask', confidence=0.0, reason='Роутер вернул не-JSON')
        data = json.loads(text[start : end + 1])
    mode = str(data.get('mode', 'ask')).lower()
    if mode not in ('append', 'new', 'ask'):
        return RouteDecision(mode='ask', confidence=0.0, reason=f'Неизвестный mode: {mode}')
    try:
        confidence = float(data.get('confidence', 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return RouteDecision(
        mode=mode,
        note_name=str(data.get('note_name', '')).strip(),
        folder=str(data.get('folder', '')).strip(),
        target_path=str(data.get('target_path', '')).strip(),
        confidence=confidence,
        reason=str(data.get('reason', '')).strip(),
    )


def validate_decision(decision: RouteDecision, catalog: list[dict[str, str]]) -> RouteDecision:
    """Сверка решения с реальным каталогом: target должен существовать, иначе ask."""
    if decision.mode == 'append':
        if not any(c['path'] == decision.target_path for c in catalog):
            return RouteDecision(
                mode='ask',
                confidence=0.0,
                reason='Роутер указал несуществующую заметку: ' + repr(decision.target_path),
            )
    if decision.mode == 'new':
        known_folders = {str(c['path']).rsplit('/', 1)[0] for c in catalog if '/' in str(c['path'])}
        if decision.folder and not any(fold.startswith(decision.folder) for fold in known_folders):
            return RouteDecision(
                mode='ask',
                confidence=0.0,
                reason='Роутер указал папку вне vault: ' + repr(decision.folder),
            )
    return decision