"""Оплата (v1.1.0): Telegram Stars — без внешних платёжек, работает из любого региона.

ЮKassa (рубли, РФ-карты) — интерфейс PaymentGateway готов, реализация — после
выбора продукта на дорожной карте (требует merchant id + ключ).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from aiogram import Bot
from aiogram.types import LabeledPrice


class Package(Enum):
    STARTER = "starter"  # бесплатный триал
    MINI = "mini"  # 10 звонков/мес
    PRO = "pro"  # 30 звонков/мес

    @property
    def stars(self) -> int:
        return {"starter": 0, "mini": 150, "pro": 350}[self.value]

    @property
    def calls_per_month(self) -> int:
        return {"starter": 3, "mini": 10, "pro": 30}[self.value]

    @property
    def title(self) -> str:
        return {
            "starter": "Старт",
            "mini": "10 звонков/мес",
            "pro": "30 звонков/мес",
        }[self.value]


@dataclass
class PaymentResult:
    ok: bool
    reason: str = ""


class PaymentGateway(Protocol):
    async def issue_invoice(self, bot: Bot, chat_id: int, package: Package) -> PaymentResult:
        """Выставить счёт за пакет. Stars: XTR; ЮKassa (v1.2): рублёвый инвойс."""
        ...


class StarsGateway:
    """Telegram Stars: инвойс в ⭐, оплата user->bot без внешнего провайдера."""

    async def issue_invoice(self, bot: Bot, chat_id: int, package: Package) -> PaymentResult:
        try:
            await bot.send_invoice(
                chat_id=chat_id,
                title=f"Пакет «{package.title}»",
                description=f"{package.calls_per_month} звонков/месяц. Продлевается вручную.",
                payload=f"package:{package.value}",
                provider_token="",  # Stars не требует провайдера
                currency="XTR",  # Telegram Stars
                prices=[LabeledPrice(label=package.title, amount=package.stars)],
            )
            return PaymentResult(ok=True)
        except Exception as e:  # noqa: BLE001
            return PaymentResult(ok=False, reason=str(e))


class YooKassaGateway:
    """Заглушка (v1.1.0 → после выбора на дорожной карте): нужны shopId + secretKey."""

    async def issue_invoice(self, bot: Bot, chat_id: int, package: Package) -> PaymentResult:
        return PaymentResult(ok=False, reason="ЮKassa не подключена: заполните YOOKASSA_SHOP_ID/YOOKASSA_SECRET")


def get_gateway(provider: str) -> PaymentGateway:
    if provider == "yookassa":
        return YooKassaGateway()
    return StarsGateway()