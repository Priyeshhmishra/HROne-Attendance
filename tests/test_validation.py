from datetime import datetime, timezone
from app.main import normalize_dt, day_key

def test_naive_datetime_is_treated_as_utc():
    result = normalize_dt(datetime(2026, 10, 15, 9, 0))
    assert result.tzinfo == timezone.utc

def test_aware_datetime_is_converted_to_utc():
    from datetime import timedelta
    result = normalize_dt(datetime(2026, 10, 15, 11, 0, tzinfo=timezone(timedelta(hours=2))))
    assert result.hour == 9
    assert result.tzinfo == timezone.utc

def test_day_key_uses_utc_date():
    assert day_key(datetime(2026, 10, 15, 9, tzinfo=timezone.utc)) == "2026-10-15"
