"""Every source row receives a disposition and explicit quality issues."""
from collections import Counter
from datetime import datetime
import numbers
import numpy as np
import pandas as pd
from openpyxl.utils.datetime import from_excel, WINDOWS_EPOCH
from team_normalization import normalize, key
COMPLETE = {'completed', 'complete', 'finished', 'ft', 'full time', 'aet', 'after extra time', 'pen', 'after penalties'}
BLOCKED = {'cancelled', 'canceled', 'abandoned', 'postponed', 'suspended', 'void'}
SCHEDULED = {'scheduled', 'upcoming', 'not started', 'ns', 'fixture', 'tbd'}

def missing(v):
    return v is None or pd.isna(v) or (isinstance(v, str) and not v.strip())

def kickoff_utc(value, timezone='UTC'):
    if missing(value):
        return pd.NaT
    try:
        if isinstance(value, numbers.Number):
            value = from_excel(float(value), epoch=WINDOWS_EPOCH)
        ts = pd.Timestamp(value)
        if pd.isna(ts) or not 1900 <= ts.year <= 2200:
            return pd.NaT
        if ts.tzinfo is None:
            ts = ts.tz_localize(timezone, ambiguous='raise', nonexistent='raise')
        return ts.tz_convert('UTC')
    except (ValueError, TypeError, OverflowError):
        return pd.NaT

def score(value):
    if missing(value):
        return np.nan, None
    try:
        num = float(value)
        if isinstance(value, bool) or not np.isfinite(num) or num < 0 or num != int(num):
            return np.nan, 'INVALID_SCORE'
        return int(num), None
    except (ValueError, TypeError):
        return np.nan, 'NON_NUMERIC_SCORE'

def validate(frame, catalog, cutoff, config):
    out = frame.copy()
    out['HOME_KEY'] = out.HOME_TEAM.map(normalize)
    out['AWAY_KEY'] = out.AWAY_TEAM.map(normalize)
    out['MATCH_ID'] = out.MATCH_ID.map(lambda v: None if missing(v) else str(v).strip())
    out['KICKOFF_UTC'] = pd.to_datetime(out.DATE_TIME.map(lambda v: kickoff_utc(v, config.source_timezone)), utc=True)
    duplicated = out.MATCH_ID.notna() & out.MATCH_ID.duplicated(keep=False)
    fixture_dup = out.duplicated(['KICKOFF_UTC', 'HOME_KEY', 'AWAY_KEY'], keep=False) & out.KICKOFF_UTC.notna()
    issues, groups, parsed_h, parsed_a = [], [], [], []
    naive_count = aware_count = 0
    for pos, (_, row) in enumerate(out.iterrows()):
        errors, notices = [], []
        if row.MATCH_ID is None: errors.append('MISSING_MATCH_ID')
        if duplicated.iloc[pos]: errors.append('DUPLICATE_MATCH_ID')
        if fixture_dup.iloc[pos]: errors.append('DUPLICATE_FIXTURE')
        if pd.isna(row.KICKOFF_UTC): errors.append('MISSING_KICKOFF' if missing(row.DATE_TIME) else 'INVALID_DATE')
        else:
            raw = row.DATE_TIME
            if isinstance(raw, (datetime, pd.Timestamp)) and raw.tzinfo is not None: aware_count += 1
            elif isinstance(raw, str) and pd.Timestamp(raw).tzinfo is not None: aware_count += 1
            else: naive_count += 1
        if not row.HOME_KEY: errors.append('MISSING_HOME_TEAM')
        if not row.AWAY_KEY: errors.append('MISSING_AWAY_TEAM')
        if row.HOME_KEY and row.HOME_KEY == row.AWAY_KEY: errors.append('SAME_TEAM')
        for side in ['HOME', 'AWAY']:
            k = row[f'{side}_KEY']
            if k and k not in catalog: notices.append(f'UNKNOWN_{side}_TEAM')
            elif k and not catalog[k]['logo']: notices.append(f'MISSING_{side}_LOGO')
        h, he = score(row.HOME_SCORE); a, ae = score(row.AWAY_SCORE)
        parsed_h.append(h); parsed_a.append(a)
        if he: errors.append('HOME_' + he)
        if ae: errors.append('AWAY_' + ae)
        both = np.isfinite(h) and np.isfinite(a)
        partial = np.isfinite(h) != np.isfinite(a)
        status = key(row.STATUS)
        if status in BLOCKED: errors.append(status.upper())
        elif status and status not in COMPLETE | SCHEDULED: errors.append('UNRECOGNIZED_OR_LIVE_STATUS')
        if partial: errors.append('INCOMPLETE_SCORES')
        season = str(row.SEASON).strip() if not missing(row.SEASON) else None
        if season is None: notices.append('MISSING_SEASON')
        elif not __import__('re').fullmatch(r'\d{4}[-/]\d{2,4}', season): notices.append('NONSTANDARD_SEASON_LABEL')
        elif pd.notna(row.KICKOFF_UTC):
            years = __import__('re').split('[-/]', season)
            start = int(years[0]); end = int(years[1]) if len(years[1]) == 4 else start // 100 * 100 + int(years[1])
            if end != start + 1 or row.KICKOFF_UTC.year not in {start, end}: notices.append('INCONSISTENT_SEASON_LABEL')
        group = 'REJECTED'
        if pd.notna(row.KICKOFF_UTC):
            if row.KICKOFF_UTC >= cutoff:
                if both: errors.append('FUTURE_MATCH_HAS_SCORES')
                if status in COMPLETE: errors.append('FUTURE_MATCH_COMPLETED')
                if not errors: group = 'UPCOMING'
            else:
                if not both: errors.append('PAST_INCOMPLETE_MATCH')
                if status in SCHEDULED: errors.append('PAST_NOT_COMPLETED')
                if row.KICKOFF_UTC + pd.Timedelta(hours=config.completion_lag_hours) > cutoff:
                    errors.append('RESULT_NOT_YET_AVAILABLE')
                if not errors: group = 'HISTORICAL'
        for code in errors + notices:
            issues.append({'excel_row': int(row['_ROW']), 'match_id': row.MATCH_ID,
                           'severity': 'ERROR' if code in errors else 'WARNING', 'code': code})
        groups.append(group)
    out['HOME_SCORE'] = parsed_h; out['AWAY_SCORE'] = parsed_a
    out['DISPOSITION'] = groups
    out['TARGET'] = np.where(out.HOME_SCORE > out.AWAY_SCORE, 0, np.where(out.HOME_SCORE == out.AWAY_SCORE, 1, 2))
    history = out[out.DISPOSITION == 'HISTORICAL'].sort_values(['KICKOFF_UTC', 'MATCH_ID']).reset_index(drop=True)
    upcoming = select_upcoming(out, config.limit)
    warnings = [f'Naive kickoff timestamps ({naive_count}) interpreted in {config.source_timezone}; aware timestamps ({aware_count}) converted to UTC.']
    if naive_count and aware_count: warnings.append('Mixed timezone representations found; all normalized to UTC.')
    if frame.STATUS.isna().all():
        warnings.append(f'No match status values. Fallback completion = past kickoff + {config.completion_lag_hours:g} hours and two valid scores. Cancellations/abandonments cannot be identified without status data; scores are trusted as recorded.')
    warnings.extend(['Only workbook UCL results are known; rest days measure time since last recorded UCL match, not domestic fixtures.',
                     'No timestamped lineup/injury data; players, goals, season_winners and standings are inspected but excluded from predictors.',
                     'Score fields may include extra time; regulation-time results cannot be reconstructed without explicit fields.',
                     'Logo references are checked for presence, not network availability.'])
    variants = {}
    for side in ['HOME', 'AWAY']:
        for name, k in zip(out[f'{side}_TEAM'], out[f'{side}_KEY']):
            if k: variants.setdefault(k, set()).add(str(name))
    report = {'cutoff_utc': cutoff.isoformat(), 'total_rows': len(out), 'valid_historical_matches': len(history),
      'invalid_historical_matches': int(((out.KICKOFF_UTC < cutoff) & (out.DISPOSITION == 'REJECTED')).sum()),
      'upcoming_fixtures': int((out.DISPOSITION == 'UPCOMING').sum()), 'selected_upcoming_fixtures': len(upcoming),
      'duplicate_matches': int((duplicated | fixture_dup).sum()), 'rejected_rows': int((out.DISPOSITION == 'REJECTED').sum()),
      'available_seasons': sorted(out.SEASON.dropna().astype(str).unique().tolist()),
      'available_teams': sorted((set(out.HOME_KEY) | set(out.AWAY_KEY)) - {''}),
      'missing_values': {c: int(frame[c].map(missing).sum()) for c in frame.columns},
      'data_quality_warnings': warnings, 'issue_counts': dict(Counter(i['code'] for i in issues)),
      'issues': issues, 'team_name_variants': {k: sorted(v) for k,v in variants.items() if len(v) > 1},
      'row_dispositions': [{'excel_row': int(r['_ROW']), 'match_id': r.MATCH_ID, 'disposition': r.DISPOSITION} for _, r in out.iterrows()]}
    return history, upcoming, report

def select_upcoming(frame, limit=18):
    result = frame[frame.DISPOSITION == 'UPCOMING'].sort_values(['KICKOFF_UTC', 'MATCH_ID'], kind='stable').head(limit)
    if result.MATCH_ID.duplicated().any(): raise AssertionError('Duplicate upcoming MATCH_ID')
    return result.reset_index(drop=True)
