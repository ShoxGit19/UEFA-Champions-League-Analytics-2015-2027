"""Paste this entire file into a Power BI Python visual.

Add HOME_LOGO_URL/AWAY_LOGO_URL or HOME_TEAM_LOGO/AWAY_TEAM_LOGO to
Values along with the prediction columns. Text fields: Don't summarize.
Desktop uses existing local photos first, then supplied URLs. Embedded PNG/JPEG
base64 columns also work without local files or networking in the Service.
No model training or workbook reads take place in this visual.
"""
import base64
import os
from functools import lru_cache
from io import BytesIO
from decimal import Decimal
from math import isfinite
from numbers import Real
from typing import TypedDict
from http.client import HTTPException
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.transforms import Bbox
from PIL import Image, UnidentifiedImageError

# Power BI executes pasted scripts in a temporary directory: use the actual
# project photo directory instead of assuming that the current directory is it.
# Set this to the local photo directory when running in Power BI Desktop.
# The repository no longer contains a machine-specific absolute path.
LOGO_DIRECTORY = Path(os.environ.get('UEFA_PHOTO_DIR', 'photo'))
ALLOW_URL_DOWNLOADS = True  # Desktop only; Service blocks outbound networking.
MAX_IMAGE_BYTES = 3 * 1024 * 1024
RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}

# Explicit existing filenames, especially where a URL is SVG or its basename
# differs from the supplied photo. Never substitute a different club's badge.
TEAM_FILES = {
    'manchestercity': ['Manchester_City_F.C.-Logo.wine_new.png'],
    'manchestercityfc': ['Manchester_City_F.C.-Logo.wine_new.png'],
    'asroma': ['AS Roma.png'],
    'barcelonafc': ['FC_Barcelona_(crest).png'],
    'fcbarcelona': ['FC_Barcelona_(crest).png'],
    'psveindhoven': ['PSV_Eindhoven.svg.png'],
    'realmadrid': ['Real_Madrid_CF.svg.webp', 'Real-Madrid-Logo.png'],
    'arsenalfc': ['Arsenal_FC.svg.webp', 'Arsenal-Logo.png'],
    'feyenoord': ['Feyenoord_logo_since_2024.svg.png'],
    'sportingcp': ['Sporting CP.jpg'],
    'bayernmunchen': ['Bayern-Munchen-Logo.png'],
    'bayernmunich': ['Bayern-Munchen-Logo.png'],
    'astonvilla': ['Aston-Villa-Logo.png'],
}

class LogoDiagnostics(TypedDict):
    requested: int
    rendered: int
    missing_teams: list[str]


class PredictionFigure(Figure):
    """Matplotlib figure with explicitly declared logo diagnostics."""
    ucl_logo_diagnostics: LogoDiagnostics


def asset_key(value):
    value = unicodedata.normalize('NFKD', str(value)).casefold()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ''.join(c for c in value if c.isalnum())

def column_key(value):
    return re.sub(r'[^A-Z0-9]+', '_', str(value).strip().upper()).strip('_')

def logo_sources(row, side):
    columns = {column_key(c): c for c in row.index}
    names = [f'{side}_LOGO_BASE64', f'{side}_TEAM_LOGO_BASE64',
             f'{side}_TEAM_LOGO', f'{side}_LOGO_URL', f'{side}_TEAM_LOGO_URL',
             f'{side}_TEAM_URL', f'{side}_LOGO']
    output = []
    for name in names:
        value = row.get(columns.get(name, name))
        if isinstance(value, str) and value.strip() and value.strip() not in output:
            output.append(value.strip())
    return output

def photo_index(directory):
    try:
        files = sorted(p for p in Path(directory).iterdir() if p.is_file() and p.suffix.lower() in RASTER_EXTENSIONS)
    except OSError:
        return {}, {}
    names = {p.name.casefold(): p for p in files}
    stems = {}
    for path in files:
        stems.setdefault(asset_key(path.stem), path)
    return names, stems

def decode_image(raw):
    if len(raw) > MAX_IMAGE_BYTES:
        return None
    try:
        with Image.open(BytesIO(raw)) as original:
            if original.width * original.height > 20_000_000:
                return None
            image = original.convert('RGBA')
            image.thumbnail((96, 96), Image.Resampling.LANCZOS)
            # Square transparent canvas keeps every badge's proportions intact.
            canvas = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
            canvas.alpha_composite(image, ((100-image.width)//2, (100-image.height)//2))
            return np.asarray(canvas).copy()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None

@lru_cache(maxsize=256)
def load_logo(source):
    try:
        if source.startswith('data:image/'):
            header, payload = source.split(',', 1)
            if ';base64' not in header.lower() or len(payload) > MAX_IMAGE_BYTES * 2:
                return None
            return decode_image(base64.b64decode(payload, validate=True))
        if source.startswith(('https://', 'http://')):
            if not ALLOW_URL_DOWNLOADS:
                return None
            request = Request(source, headers={'User-Agent': 'Mozilla/5.0 UCLPredictionCenter/2.0'})
            with urlopen(request, timeout=2) as response:
                return decode_image(response.read(MAX_IMAGE_BYTES + 1))
        if len(source) > 80 and source.startswith(('iVBOR', '/9j/', 'R0lGOD', 'UklGR', 'Qk')):
            return decode_image(base64.b64decode(source, validate=True))
        path = Path(source)
        if path.is_file() and path.stat().st_size <= MAX_IMAGE_BYTES:
            return decode_image(path.read_bytes())
        # Optional raw base64 from Power Query. No network is needed for this.
        if len(source) > 80 and len(source) <= MAX_IMAGE_BYTES * 2:
            return decode_image(base64.b64decode(source, validate=True))
    except (OSError, ValueError, TimeoutError, HTTPException):
        pass
    return None

def resolve_logo(team, sources, names, stems):
    # Embedded data is portable and needs neither a filesystem nor network.
    embedded = [s for s in sources if s.startswith('data:image/') or (len(s)>80 and s.startswith(('iVBOR', '/9j/', 'R0lGOD', 'UklGR', 'Qk')))]
    for source in embedded:
        image = load_logo(source)
        if image is not None:
            return image
    filenames = list(TEAM_FILES.get(asset_key(team), []))
    for source in sources:
        if source.startswith('data:'):
            continue
        try:
            filename = unquote(urlsplit(source).path).replace('\\', '/').rsplit('/', 1)[-1]
        except ValueError:
            # A malformed URL must not prevent the local team badge fallback.
            continue
        if filename:
            filenames.append(filename)
    candidates = [names.get(name.casefold()) or stems.get(asset_key(Path(name).stem)) for name in filenames]
    candidates.append(stems.get(asset_key(team)))
    for path in candidates:
        if path is not None:
            image = load_logo(str(path))
            if image is not None:
                return image
    for source in sources:
        if source not in embedded:
            image = load_logo(source)
            if image is not None:
                return image
    return None

def text_value(value, default=''):
    """Power BI can supply None, NaN or pd.NA even in text columns."""
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    return text if text else default

def finite_number(value: object) -> float | None:
    """Convert a scalar without pandas array/Series overload ambiguity."""
    if not isinstance(value, (str, Real, Decimal)):
        return None
    try:
        numeric = float(value)
    except (ValueError, OverflowError):
        return None
    return numeric if isfinite(numeric) else None

def number(row, name, percentage=False, decimals=2):
    value = finite_number(row.get(name))
    if value is None:
        return 'N/A'
    return f'{value:.0%}' if percentage else f'{value:.{decimals}f}'

def predicted_score(row):
    home = finite_number(row.get('PREDICTED_HOME_GOALS'))
    away = finite_number(row.get('PREDICTED_AWAY_GOALS'))
    if home is None or away is None or min(home, away) < 0:
        return 'N/A'
    if not home.is_integer() or not away.is_integer():
        return 'N/A'
    return f'{int(home)}-{int(away)}'

def render_predictions(dataset, logo_directory=None, logo_resolver=None) -> PredictionFigure:
    data = dataset.copy()
    data['DATE_TIME'] = pd.to_datetime(data.get('DATE_TIME'), errors='coerce', utc=True)
    if 'MATCH_ID' in data:
        data['MATCH_ID'] = data.MATCH_ID.astype(str)
    sort = ['DATE_TIME'] + (['MATCH_ID'] if 'MATCH_ID' in data else [])
    data = data.sort_values(sort, kind='stable').head(18)
    names, stems = photo_index(LOGO_DIRECTORY if logo_directory is None else logo_directory)
    badges = []
    rows = []
    missing = set()
    for _, r in data.iterrows():
        status = text_value(r.get('MODEL_STATUS'), text_value(r.get('PREDICTION_STATUS'), 'PREDICTION_UNAVAILABLE'))
        score = predicted_score(r)
        date = r.DATE_TIME.strftime('%d %b %H:%M') if pd.notna(r.DATE_TIME) else 'N/A'
        pair = []
        for side in ['HOME', 'AWAY']:
            team = text_value(r.get(f'{side}_TEAM'))
            sources = logo_sources(r, side)
            image = logo_resolver(team, sources) if logo_resolver else resolve_logo(team, sources, names, stems)
            pair.append(image)
            if image is None:
                missing.add(team)
        badges.append(pair)
        rows.append([date, '' if pair[0] is not None else '?', text_value(r.get('HOME_TEAM')),
            '' if pair[1] is not None else '?', text_value(r.get('AWAY_TEAM')),
            number(r,'HOME_WIN_PROB',True), number(r,'DRAW_PROB',True), number(r,'AWAY_WIN_PROB',True),score,
            number(r,'EXACT_SCORE_PROB',True), f'{number(r,"EXPECTED_HOME_GOALS")} / {number(r,"EXPECTED_AWAY_GOALS")}',
            number(r,'MODEL_CONFIDENCE',True),status])
    fig, ax = plt.subplots(figsize=(22, max(3.5, 2.0+len(rows)*.5)), FigureClass=PredictionFigure)
    if not isinstance(fig, PredictionFigure):
        raise TypeError('Expected a PredictionFigure from Matplotlib')
    fig.patch.set_facecolor('#0b1220'); ax.set_facecolor('#0b1220'); ax.axis('off')
    ax.set_title('UCL Prediction Center - Statistical match forecasts', color='white', fontsize=17, pad=18, loc='left')
    table = None
    if rows:
        labels = ['Kickoff UTC', '', 'Home', '', 'Away', 'Home win', 'Draw', 'Away win', 'Likely score', 'Score prob.', 'Expected goals H/A', 'Confidence*', 'Status']
        widths = np.array([9,3,14,3,14,6,5,6,7,7,10,7,10], dtype=float)
        table = ax.table(cellText=rows, colLabels=labels, cellLoc='center', colWidths=widths/widths.sum(), bbox=Bbox.from_bounds(0,.02,1,.94))
        table.auto_set_font_size(False); table.set_fontsize(9)
        for (row,col), cell in table.get_celld().items():
            cell.set_edgecolor('#243248'); cell.set_facecolor('#17243b' if row==0 else '#101b2e' if row%2 else '#132139')
            cell.get_text().set_color('#e7edf7')
            if row==0:
                cell.get_text().set_fontweight('bold')
            if row>0 and col==12 and rows[row-1][-1]!='READY':
                cell.get_text().set_color('#ffce73')
    else:
        ax.text(.5,.5,'No upcoming fixtures in the refreshed predictions table.',color='white',ha='center',transform=ax.transAxes)
    fig.text(.02,.035,'Scores are statistical estimates, not guaranteed results. *Confidence is a data-quality heuristic. LOW_DATA requires caution.',color='#b7c6da',fontsize=9)
    rendered = sum(image is not None for pair in badges for image in pair)
    if missing:
        details = ', '.join(sorted(missing))
        if len(details) > 160:
            details = details[:157]+'...'
        fig.text(.02,.012,f'Logos: {rendered}/{2*len(rows)}. Unavailable: {details}. Check logo fields or photo directory.',color='#ffce73',fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.97))
    # Resolve layout first. Placing badges before this step overlays the wrong
    # cells when Power BI changes image dimensions or tight_layout moves axes.
    if table is not None:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer() if isinstance(fig.canvas, FigureCanvasAgg) else None
        for row_number, pair in enumerate(badges, 1):
            for column, image in zip([1,3], pair):
                if image is None:
                    continue
                cell = table[row_number,column]
                bounds = cell.get_window_extent(renderer)
                coordinates = ax.transAxes.inverted().transform([(bounds.x0+bounds.x1)/2,(bounds.y0+bounds.y1)/2])
                center = (float(coordinates[0]), float(coordinates[1]))
                size_points = min(bounds.width,bounds.height)*72/fig.dpi*.82
                box = OffsetImage(image, zoom=size_points/image.shape[0], interpolation='lanczos')
                badge = AnnotationBbox(box, center, xycoords=ax.transAxes, frameon=False, pad=0, annotation_clip=False)
                badge.set_in_layout(False)
                ax.add_artist(badge)
    # Plain metadata supports meaningful rendering checks without pixel guessing.
    fig.ucl_logo_diagnostics = {'requested':2*len(rows), 'rendered':rendered, 'missing_teams':sorted(missing)}
    return fig

# Power BI injects this name; IDEs do not have a module-level dataset.
power_bi_dataset = globals().get('dataset')
if isinstance(power_bi_dataset, pd.DataFrame):
    render_predictions(power_bi_dataset)
    plt.show()
