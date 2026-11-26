"""Explicit aliases; no fuzzy joins that could merge different clubs."""
import re
import unicodedata
import pandas as pd

def key(value):
    if value is None or pd.isna(value):
        return ''
    text = unicodedata.normalize('NFKD', str(value).strip()).casefold()
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^\w]+', ' ', text).strip()

_GROUPS = {
    'Bayern Munich': ['Bayern M\u00fcnchen', 'FC Bayern M\u00fcnchen', 'Bayern Munich'],
    'Paris Saint-Germain': ['Paris Saint-Germain', 'PSG'],
    'Manchester City': ['Manchester City FC', 'Manchester City'],
    'Liverpool': ['Liverpool FC', 'Liverpool'],
    'Sporting CP': ['Sporting CP', 'Sporting Lisbon'],
    'Inter Milan': ['Inter', 'Inter Milan', 'Internazionale'],
    'Club Brugge': ['Club Brugge', 'Club Brugge KV'],
}
ALIASES = {key(alias): canonical for canonical, aliases in _GROUPS.items() for alias in aliases}

def normalize(value):
    k = key(value)
    return ALIASES.get(k, k)

def team_catalog(frame):
    if frame is None or frame.empty:
        return {}, ['teams sheet is empty; team identity and logos cannot be verified.']
    from schema_mapper import header_key
    cols = {header_key(c): c for c in frame.columns}
    name = next((cols[c] for c in ['TEAM_NAME', 'NAME', 'TEAM', 'CLUB_NAME'] if c in cols), None)
    logo = next((cols[c] for c in ['TEAM_URL', 'TEAM_LOGO', 'LOGO', 'LOGO_URL', 'IMAGE_URL'] if c in cols), None)
    if name is None:
        return {}, ['teams sheet has no recognized name column.']
    catalog, warnings = {}, []
    for _, row in frame.iterrows():
        k = normalize(row[name])
        if not k:
            warnings.append('Blank team name in teams sheet.')
            continue
        url = row.get(logo) if logo else None
        url = str(url).strip() if pd.notna(url) and str(url).strip() else None
        if k in catalog:
            warnings.append(f'Duplicate canonical team in teams sheet: {row[name]}')
        catalog[k] = {'name': str(row[name]), 'logo': url}
    return catalog, warnings
