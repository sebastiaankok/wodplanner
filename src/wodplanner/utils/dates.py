from datetime import date, datetime

API_DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def parse_iso_date(s: str) -> date:
    return date.fromisoformat(s)


def parse_iso_datetime(s: str) -> datetime:
    return datetime.fromisoformat(s)


def parse_api_datetime(s: str) -> datetime:
    return datetime.strptime(s, API_DATETIME_FORMAT)


def fmt_api_datetime(dt: datetime) -> str:
    return dt.strftime(API_DATETIME_FORMAT)