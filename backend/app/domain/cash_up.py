"""Spec Part A §8: daily cash-up."""

from dataclasses import dataclass

from app.domain.money import Cents


@dataclass(frozen=True)
class CashUpResult:
    expected: Cents
    counted: Cents
    variance: Cents  # counted - expected: negative is a shortage, positive an overage

    @property
    def shortage(self) -> Cents:
        return max(0, -self.variance)

    @property
    def overage(self) -> Cents:
        return max(0, self.variance)


def cash_up(expected: Cents, counted: Cents, explanation: str | None) -> CashUpResult:
    if counted < 0:
        raise ValueError("counted balance cannot be negative")
    result = CashUpResult(expected, counted, counted - expected)
    if result.variance and not (explanation or "").strip():
        raise ValueError("a variance needs an explanation")
    return result
