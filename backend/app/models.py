from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class Principal:
    subject: str
    customer_id: int
    username: str


@dataclass
class SessionRecord:
    access_token: str
    refresh_token: str
    expires_at: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SessionRecord":
        return cls(
            access_token=str(value["access_token"]),
            refresh_token=str(value.get("refresh_token", "")),
            expires_at=float(value["expires_at"]),
        )


@dataclass(frozen=True)
class ReportRow:
    report_date: date
    customer_name: str
    customer_email: str
    prosthesis_count: int
    measurement_count: int
    avg_signal_frequency: float
    avg_signal_duration: float
    avg_signal_amplitude: float
    last_signal_at: datetime

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReportRow":
        return cls(
            report_date=date.fromisoformat(str(value["report_date"])),
            customer_name=str(value["customer_name"]),
            customer_email=str(value["customer_email"]),
            prosthesis_count=int(value["prosthesis_count"]),
            measurement_count=int(value["measurement_count"]),
            avg_signal_frequency=float(value["avg_signal_frequency"]),
            avg_signal_duration=float(value["avg_signal_duration"]),
            avg_signal_amplitude=float(value["avg_signal_amplitude"]),
            last_signal_at=datetime.fromisoformat(str(value["last_signal_at"])),
        )
