from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import bad_request
from app.models import Click, Link
from app.schemas import (
    MAX_DAILY_RANGE,
    MAX_HOURLY_RANGE,
    CountItem,
    StatsOut,
    TimeBucket,
)


def _top(session: Session, column, where, limit: int, null_label: str) -> list[CountItem]:
    clicks = func.count().label("clicks")
    rows = session.execute(
        select(column, clicks).where(*where).group_by(column).order_by(clicks.desc(), column).limit(limit)
    ).all()
    return [CountItem(value=value or null_label, clicks=count) for value, count in rows]


def link_stats(
    session: Session,
    link: Link,
    start: datetime,
    end: datetime,
    granularity: str,
    top_n: int = 10,
) -> StatsOut:
    if start >= end:
        raise bad_request("'from' must be earlier than 'to'")
    limit = MAX_HOURLY_RANGE if granularity == "hour" else MAX_DAILY_RANGE
    if end - start > limit:
        raise bad_request(f"Range too large for {granularity} granularity (max {limit.days} days)")

    where = (Click.link_id == link.id, Click.clicked_at >= start, Click.clicked_at <= end)

    bucket_col = Click.hour_bucket if granularity == "hour" else Click.day_bucket
    counts = {b: c for b, c in session.execute(select(bucket_col, func.count()).where(*where).group_by(bucket_col))}

    series: list[TimeBucket] = []
    if granularity == "hour":
        cursor = start.replace(minute=0, second=0, microsecond=0)
        while cursor <= end:
            series.append(TimeBucket(bucket=cursor, clicks=counts.get(cursor, 0)))
            cursor += timedelta(hours=1)
    else:
        day = start.date()
        while day <= end.date():
            series.append(
                TimeBucket(bucket=datetime.combine(day, time.min, tzinfo=timezone.utc), clicks=counts.get(day, 0))
            )
            day += timedelta(days=1)

    in_range, unique = session.execute(
        select(func.count(), func.count(func.distinct(Click.visitor_hash))).where(*where)
    ).one()

    return StatsOut(
        short_code=link.short_code,
        total_clicks=link.click_count,
        range_start=start,
        range_end=end,
        granularity=granularity,  # type: ignore[arg-type]
        clicks_in_range=in_range,
        unique_visitors_in_range=unique,
        timeseries=series,
        referrers=_top(session, Click.referrer_host, where, top_n, "direct"),
        browsers=_top(session, Click.browser, where, top_n, "unknown"),
        operating_systems=_top(session, Click.os, where, top_n, "unknown"),
        devices=_top(session, Click.device, where, top_n, "unknown"),
        countries=_top(session, Click.country, where, top_n, "unknown"),
    )
