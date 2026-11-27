"""Runtime configuration. Workbook dates are UTC, confirmed by the owner."""
from dataclasses import dataclass
from pathlib import Path
VERSION = "2.0.0"
TITLE = "UCL Prediction Center - Professional Match Prediction Model"
BASE_COLUMNS = "MATCH_ID DATE_TIME SEASON HOME_TEAM AWAY_TEAM STADIUM HOME_WIN_PROB DRAW_PROB AWAY_WIN_PROB EXPECTED_HOME_GOALS EXPECTED_AWAY_GOALS PREDICTED_HOME_GOALS PREDICTED_AWAY_GOALS MODEL_NAME MODEL_VERSION PREDICTION_STATUS".split()
EXTRA_COLUMNS = (['EXACT_SCORE_PROB'] + [v for i in range(1, 6) for v in (f'TOP_SCORE_{i}', f'TOP_SCORE_{i}_PROB')] + "BOTH_TEAMS_SCORE_PROB OVER_2_5_PROB UNDER_2_5_PROB OVER_3_5_PROB CLEAN_SHEET_HOME_PROB CLEAN_SHEET_AWAY_PROB MODEL_CONFIDENCE DATA_COVERAGE PREDICTION_CREATED_AT SOURCE_SEASON TRAINING_SAMPLE_COUNT MODEL_STATUS HOME_TEAM_LOGO AWAY_TEAM_LOGO SCORE_MATRIX_JSON CONFIDENCE_COMPONENTS_JSON".split())
OUTPUT_COLUMNS = BASE_COLUMNS + EXTRA_COLUMNS
OUTCOMES = ['H', 'D', 'A']
MODEL_NAMES = ['Historical baseline', 'Elo', 'Poisson', 'Logistic Regression', 'HistGradientBoostingClassifier']
@dataclass(frozen=True)
class Config:
    workbook: Path
    output_dir: Path
    source_timezone: str = 'UTC'
    limit: int = 18
    completion_lag_hours: float = 3.0
    minimum_training: int = 100
    coverage_matches: int = 5
    seed: int = 42

def discover_workbook(directory):
    paths = [p for p in Path(directory).glob('*.xlsx') if not p.name.startswith('~$') and '_backup_' not in p.stem and '.pending' not in p.stem and not p.stem.endswith('_predictions_ready')]
    if len(paths) != 1:
        raise ValueError(f'Expected exactly one source .xlsx in {directory}; found {len(paths)}. Use --workbook PATH.')
    return paths[0].resolve()
