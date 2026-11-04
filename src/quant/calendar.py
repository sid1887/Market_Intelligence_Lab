import datetime
from typing import Set, Dict, List, Tuple, Any

# Official NSE Trading Holidays (Capital Market Segment)
# Ref Circular: NSE/CMTR/71775, election notification circulars, and official holiday schedules.
NSE_HOLIDAYS: Dict[str, str] = {
    # 2024 (Post-Oct 21 Baseline)
    "2024-11-15": "Prakash Gurpurb Sri Guru Nanak Dev Jayanti",
    "2024-11-20": "Maharashtra Assembly General Election",
    "2024-12-25": "Christmas",

    # 2025 Official Weekday Holidays (Diwali Muhurat Trading on 2025-10-21 is a special session, not a closed holiday)
    "2025-01-26": "Republic Day",
    "2025-02-26": "Mahashivratri",
    "2025-03-14": "Holi",
    "2025-03-31": "Id-Ul-Fitr (Ramzan Id)",
    "2025-04-10": "Mahavir Jayanti",
    "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2025-04-18": "Good Friday",
    "2025-05-01": "Maharashtra Day",
    "2025-06-07": "Bakri Id (Id-Ul-Zuha)",
    "2025-08-15": "Independence Day",
    "2025-08-27": "Ganesh Chaturthi",
    "2025-10-02": "Mahatma Gandhi Jayanti / Dussehra",
    "2025-10-22": "Diwali Balipratipada",
    "2025-11-05": "Prakash Gurpurb Sri Guru Nanak Dev Jayanti",
    "2025-12-25": "Christmas",

    # 2026 Official Weekday Holidays (Circular NSE/CMTR/71775)
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas"
}

# Special exchange trading sessions (Diwali Muhurat Trading & Union Budget weekend sessions)
SPECIAL_TRADING_SESSIONS: Dict[str, str] = {
    "2024-11-01": "Special Session (Diwali Muhurat Trading)",
    "2025-02-01": "Special Weekend Session (Union Budget)",
    "2025-10-21": "Special Session (Diwali Muhurat Trading)",
    "2026-02-01": "Special Weekend Session (Union Budget)"
}

def parse_date(date_str: str) -> datetime.date:
    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

def is_weekend(d: datetime.date) -> bool:
    return d.weekday() >= 5  # 5=Saturday, 6=Sunday

def is_trading_holiday(date_str: str) -> Tuple[bool, str]:
    if date_str in NSE_HOLIDAYS:
        return True, NSE_HOLIDAYS[date_str]
    return False, ""

def is_trading_session(date_str: str) -> Tuple[bool, str]:
    """
    Checks whether a date is a valid NSE trading session.
    Returns (is_trading, reason).
    """
    try:
        d = parse_date(date_str)
    except Exception as e:
        return False, f"Invalid date format: {date_str}"

    # Special exchange trading sessions (Muhurat trading, Budget sessions on weekends)
    if date_str in SPECIAL_TRADING_SESSIONS:
        return True, SPECIAL_TRADING_SESSIONS[date_str]

    if is_weekend(d):
        day_name = d.strftime("%A")
        return False, f"Weekend ({day_name})"

    is_hol, reason = is_trading_holiday(date_str)
    if is_hol:
        return False, f"Exchange Holiday ({reason})"

    return True, "Trading Session"

def get_intermediate_trading_sessions(start_date: str, end_date: str) -> List[str]:
    """
    Returns the list of trading session dates strictly between start_date and end_date
    (i.e., start_date < d < end_date).
    """
    try:
        start_d = parse_date(start_date)
        end_d = parse_date(end_date)
    except Exception:
        return []

    if start_d >= end_d:
        return []

    curr_d = start_d + datetime.timedelta(days=1)
    sessions: List[str] = []
    while curr_d < end_d:
        d_str = curr_d.strftime("%Y-%m-%d")
        is_tr, _ = is_trading_session(d_str)
        if is_tr:
            sessions.append(d_str)
        curr_d += datetime.timedelta(days=1)
    return sessions

def count_trading_sessions_between(start_date: str, end_date: str) -> int:
    """
    Counts the number of trading sessions elapsed from start_date to end_date.
    Returns:
      0 if start_date == end_date
      Strictly positive integer if start_date < end_date (counting sessions strictly after start_date up to and including end_date)
      0 if start_date > end_date
    """
    try:
        start_d = parse_date(start_date)
        end_d = parse_date(end_date)
    except Exception:
        return 0

    if start_d >= end_d:
        return 0

    curr_d = start_d + datetime.timedelta(days=1)
    count = 0
    while curr_d <= end_d:
        d_str = curr_d.strftime("%Y-%m-%d")
        is_tr, _ = is_trading_session(d_str)
        if is_tr:
            count += 1
        curr_d += datetime.timedelta(days=1)
    return count

def validate_trading_calendar(observed_dates: List[str]) -> Dict[str, Any]:
    """
    Validates observed trading dates against calendar weekdays (Mon-Fri) and special sessions.
    Reconciles all missing weekdays against official published NSE holidays.
    """
    if not observed_dates:
        return {
            "status": "EMPTY",
            "observed_count": 0,
            "expected_weekdays": 0,
            "known_holidays_count": 0,
            "known_holidays": [],
            "special_weekend_sessions": [],
            "unexpected_missing_count": 0,
            "unexpected_missing": [],
            "valid": False
        }

    sorted_dates = sorted(list(set(observed_dates)))
    start_d = parse_date(sorted_dates[0])
    end_d = parse_date(sorted_dates[-1])

    curr_d = start_d
    expected_weekdays: List[str] = []
    special_weekend_sessions: List[str] = []

    while curr_d <= end_d:
        d_str = curr_d.strftime("%Y-%m-%d")
        if not is_weekend(curr_d):
            expected_weekdays.append(d_str)
        elif d_str in SPECIAL_TRADING_SESSIONS:
            special_weekend_sessions.append(d_str)
        curr_d += datetime.timedelta(days=1)

    observed_set: Set[str] = set(sorted_dates)
    missing_weekdays = [d for d in expected_weekdays if d not in observed_set]

    known_holidays: List[Dict[str, str]] = []
    unexpected_missing: List[str] = []

    for d_str in missing_weekdays:
        is_hol, reason = is_trading_holiday(d_str)
        if is_hol:
            known_holidays.append({"date": d_str, "reason": reason})
        else:
            unexpected_missing.append(d_str)

    expected_sessions = len(expected_weekdays) - len(known_holidays) + len(special_weekend_sessions)

    return {
        "start_date": sorted_dates[0],
        "end_date": sorted_dates[-1],
        "observed_count": len(sorted_dates),
        "expected_weekdays": len(expected_weekdays),
        "known_holidays_count": len(known_holidays),
        "known_holidays": known_holidays,
        "special_weekend_sessions": special_weekend_sessions,
        "expected_trading_sessions": expected_sessions,
        "unexpected_missing_count": len(unexpected_missing),
        "unexpected_missing": unexpected_missing,
        "reconciliation_summary": (
            f"{len(expected_weekdays)} weekdays - {len(known_holidays)} holidays + "
            f"{len(special_weekend_sessions)} special weekend sessions = "
            f"{expected_sessions} expected sessions. Observed: {len(sorted_dates)} sessions. "
            f"Unexplained discrepancy: {len(unexpected_missing)} days."
        ),
        "valid": len(unexpected_missing) == 0 and len(sorted_dates) == expected_sessions
    }
