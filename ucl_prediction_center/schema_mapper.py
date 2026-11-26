"""Map by header; prefer DATE_TIME to the redundant MATCH_DATE column."""
import re
import pandas as pd
ALIASES = {
 'MATCH_ID': ['MATCH_ID', 'MATCHID', 'FIXTURE_ID', 'GAME_ID'],
 'DATE_TIME': ['DATE_TIME', 'KICKOFF', 'KICK_OFF', 'DATETIME', 'MATCH_DATE', 'DATE'],
 'HOME_TEAM': ['HOME_TEAM', 'HOME_TEAM_NAME', 'HOME', 'HOST_TEAM'],
 'AWAY_TEAM': ['AWAY_TEAM', 'AWAY_TEAM_NAME', 'AWAY', 'VISITOR_TEAM'],
 'HOME_SCORE': ['HOME_TEAM_SCORE', 'HOME_SCORE', 'HOME_GOALS', 'FTHG'],
 'AWAY_SCORE': ['AWAY_TEAM_SCORE', 'AWAY_SCORE', 'AWAY_GOALS', 'FTAG'],
 'SEASON': ['SEASON', 'SEASON_NAME', 'YEAR'],
 'STADIUM': ['STADIUM', 'VENUE', 'STADIUM_NAME'],
 'STAGE': ['STAGE', 'ROUND', 'PHASE'],
 'STATUS': ['MATCH_STATUS', 'STATUS', 'FIXTURE_STATUS', 'COMPLETION_STATUS'],
 'NEUTRAL': ['NEUTRAL', 'NEUTRAL_VENUE', 'IS_NEUTRAL'],
}
def header_key(value):
    return re.sub(r'[^A-Z0-9]+', '_', str(value).strip().upper()).strip('_')

def map_matches(frame):
    lookup = {}
    for col in frame.columns:
        k = header_key(col)
        if k in lookup:
            raise ValueError(f'Ambiguous duplicate match header: {col}')
        lookup[k] = col
    mapping, warnings = {}, []
    for target, aliases in ALIASES.items():
        hits = [lookup[a] for a in aliases if a in lookup]
        if hits:
            mapping[target] = hits[0]
            if len(hits) > 1:
                warnings.append(f'{target}: chose {hits[0]} over {hits[1:]}.')
    missing = [k for k in ['MATCH_ID', 'DATE_TIME', 'HOME_TEAM', 'AWAY_TEAM'] if k not in mapping]
    if missing:
        raise ValueError('Required matches columns missing: ' + ', '.join(missing))
    out = pd.DataFrame({k: frame[v] for k, v in mapping.items()})
    for k in ALIASES:
        if k not in out:
            out[k] = None
            warnings.append(f'{k} column absent: ' + ('historical scores unavailable; no results invented.' if 'SCORE' in k else 'field remains missing; documented fallback applies.'))
    out['_ROW'] = frame.index + 2
    return out, mapping, warnings
