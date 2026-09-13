"""Session-local fictional data and account-opening state transitions."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class Tenant(StrEnum):
    BANK_A = "bank_a"
    BANK_B = "bank_b"


class Drift(StrEnum):
    NONE = "none"
    LABEL_DRIFT = "label"
    STRUCTURAL_DRIFT = "structural"
    AMBIGUOUS_DRIFT = "ambiguous"


class Fault(StrEnum):
    NONE = "NONE"
    SLOW_PAGE = "SLOW_PAGE"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNEXPECTED_MODAL = "UNEXPECTED_MODAL"
    AMBIGUOUS_CONTROL = "AMBIGUOUS_CONTROL"
    STALE_MEMBER = "STALE_MEMBER"
    ALL_LOCATORS_FAILED = "ALL_LOCATORS_FAILED"
    REQUIRED_ELEMENT_MISSING = "REQUIRED_ELEMENT_MISSING"
    PARTIAL_PAGE = "PARTIAL_PAGE"
    UNEXPECTED_PAGE = "UNEXPECTED_PAGE"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    VALUE_NOT_RETAINED = "VALUE_NOT_RETAINED"


@dataclass(frozen=True)
class Member:
    identifier: str
    display_name: str
    savings_balance: Decimal
    eligible: bool = True


MEMBERS = {
    "48321": Member("48321", "Fictional Member ALPHA", Decimal("1420.75")),
    "83921": Member("83921", "Fictional Member BETA", Decimal("807.20")),
    "77777": Member("77777", "Fictional Member GAMMA", Decimal("65.00"), False),
}


class Stage(StrEnum):
    SEARCH = "search"
    DETAILS = "details"
    OPENING = "opening"
    REVIEW = "review"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


@dataclass
class Counters:
    search: int = 0
    begin: int = 0
    review: int = 0
    confirm: int = 0
    opened: int = 0


@dataclass(frozen=True)
class SavingsSubaccount:
    identifier: str
    member_id: str
    balance: Decimal


@dataclass
class Session:
    tenant: Tenant = Tenant.BANK_A
    drift: Drift = Drift.NONE
    application_version: str = "1"
    fault: Fault = Fault.NONE
    fallback: bool = False
    stage: Stage = Stage.SEARCH
    member: Member | None = None
    deposit: Decimal | None = None
    receipt: str | None = None
    counters: Counters = field(default_factory=Counters)
    subaccounts: list[SavingsSubaccount] = field(default_factory=list)

    def search(self, identifier: str) -> str:
        self.counters.search += 1
        self.member = None
        self.deposit = None
        self.receipt = None
        if self.fault == Fault.SESSION_EXPIRED:
            self.stage = Stage.EXPIRED
            return "SESSION_EXPIRED"
        self.member = MEMBERS.get("83921" if self.fault == Fault.STALE_MEMBER else identifier)
        self.stage = Stage.DETAILS if self.member else Stage.SEARCH
        return "DETAILS" if self.member else "MEMBER_NOT_FOUND"

    def begin(self) -> str:
        self.counters.begin += 1
        if self.stage != Stage.DETAILS or self.member is None:
            return "INVALID_STATE"
        if self.fault == Fault.PERMISSION_DENIED:
            return "PERMISSION_DENIED"
        if not self.member.eligible:
            return "MEMBER_INELIGIBLE"
        self.stage = Stage.OPENING
        return "OPENING"

    def review(self, value: str) -> str:
        self.counters.review += 1
        if self.stage != Stage.OPENING or self.member is None or not self.member.eligible:
            return "INVALID_STATE"
        try:
            deposit = Decimal(value)
            if not deposit.is_finite() or not Decimal("0.01") <= deposit <= Decimal("1000000"):
                return "INVALID_DEPOSIT"
            if deposit != deposit.quantize(Decimal("0.01")):
                return "INVALID_DEPOSIT"
        except InvalidOperation:
            return "INVALID_DEPOSIT"
        self.deposit = deposit.quantize(Decimal("0.01"))
        self.stage = Stage.REVIEW
        return "REVIEW"

    def confirm(self) -> str:
        self.counters.confirm += 1
        if self.stage != Stage.REVIEW or self.member is None or self.deposit is None:
            return "INVALID_STATE"
        self.counters.opened += 1
        self.subaccounts.append(SavingsSubaccount(
            identifier=f"SIM-SAV-{self.counters.opened:04d}",
            member_id=self.member.identifier, balance=self.deposit,
        ))
        self.receipt = f"SIM-OPEN-{self.counters.opened:04d}"
        self.stage = Stage.CONFIRMED
        return "CONFIRMED"
