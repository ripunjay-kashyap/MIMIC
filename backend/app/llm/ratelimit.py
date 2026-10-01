"""Async token buckets: queue (never error) when a provider's RPM/TPM would be exceeded."""

import asyncio
import time


class Bucket:
    def __init__(self, per_minute: float) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self.level = float(per_minute)
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self.level = min(self.capacity, self.level + (now - self.updated) * self.rate)
        self.updated = now

    def wait_time(self, amount: float) -> float:
        self._refill()
        amount = min(amount, self.capacity)
        return 0.0 if self.level >= amount else (amount - self.level) / self.rate

    async def acquire(self, amount: float) -> None:
        amount = min(amount, self.capacity)
        async with self.lock:
            while True:
                wait = self.wait_time(amount)
                if wait <= 0:
                    self.level -= amount
                    return
                await asyncio.sleep(wait)

    def refund(self, amount: float) -> None:
        """Give back over-reserved tokens once the real usage is known."""
        self._refill()
        self.level = min(self.capacity, self.level + max(0.0, amount))


class ModelLimiter:
    """RPM + TPM buckets for one (provider, model)."""

    def __init__(self, rpm: float, tpm: float) -> None:
        self.rpm = Bucket(rpm)
        self.tpm = Bucket(tpm)

    def wait_time(self, tokens: int) -> float:
        return max(self.rpm.wait_time(1), self.tpm.wait_time(tokens))

    async def acquire(self, tokens: int) -> None:
        await self.rpm.acquire(1)
        await self.tpm.acquire(tokens)

    def settle(self, reserved: int, actual: int) -> None:
        if actual < reserved:
            self.tpm.refund(reserved - actual)


_limiters: dict[str, ModelLimiter] = {}


def limiter(key: str, rpm: float, tpm: float) -> ModelLimiter:
    if key not in _limiters:
        _limiters[key] = ModelLimiter(rpm, tpm)
    return _limiters[key]
