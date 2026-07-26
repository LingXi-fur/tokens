"""按 日 / 周 / 月 聚合，附带按模型、按源拆分。"""
from collections import defaultdict
from datetime import date, timedelta


def week_start(d):
    """周一为周首。"""
    return d - timedelta(days=d.weekday())


def month_start(d):
    return d.replace(day=1)


def add_months(d, months):
    """日期减/加 N 个月（按月首对齐）。months 可为负。"""
    idx = d.month - 1 + months
    y = d.year + idx // 12
    m = idx % 12 + 1
    return date(y, m, 1)


def filter_range(records, since=None, until=None):
    res = []
    for r in records:
        d = r["date"]
        if since and d < since:
            continue
        if until and d > until:
            continue
        res.append(r)
    return res


def summarize(records):
    total = 0
    by_model = defaultdict(int)
    by_source = defaultdict(int)
    cache_read = 0
    cache_write = 0
    for r in records:
        t = r["total"]
        total += t
        by_model[r["model"]] += t
        by_source[r["source"]] += t
        cache_read += r.get("cache_read", 0) or 0
        cache_write += r.get("cache_write", 0) or 0
    by_model = sorted(by_model.items(), key=lambda kv: kv[1], reverse=True)
    by_source = sorted(by_source.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "total": total,
        "by_model": by_model,
        "by_source": by_source,
        "calls": len(records),
        "cache_read": cache_read,
        "cache_write": cache_write,
    }


def top_by(records, key, limit=8):
    """按 record[key] 聚合 total，返回 [(label, total)] 降序 top-N。key 为 None 的跳过。"""
    buckets = defaultdict(int)
    for r in records:
        k = r.get(key)
        if not k:
            continue
        buckets[k] += r["total"]
    return sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)[:limit]


def by_day(records):
    buckets = defaultdict(list)
    for r in records:
        buckets[r["date"]].append(r)
    return [(d, summarize(recs)) for d, recs in sorted(buckets.items())]


def by_week(records):
    buckets = defaultdict(list)
    for r in records:
        d = date.fromisoformat(r["date"])
        buckets[week_start(d).isoformat()].append(r)
    return [(w, summarize(recs)) for w, recs in sorted(buckets.items())]


def by_month(records):
    buckets = defaultdict(list)
    for r in records:
        d = date.fromisoformat(r["date"])
        buckets[month_start(d).isoformat()].append(r)
    return [(m, summarize(recs)) for m, recs in sorted(buckets.items())]


def grand_total(records):
    return summarize(records)
