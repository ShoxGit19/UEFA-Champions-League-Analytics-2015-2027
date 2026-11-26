# UCL Prediction Center - Professional Match Prediction Model

This external Python application reads the existing workbook, validates every match, builds strictly pre-match features, compares five models chronologically, and updates the same `Predictions` Excel table. `python main.py` discovers the source workbook in the parent directory; backups are excluded from discovery. All original sheets and source values remain present. Extra output columns start after existing columns (Q in the supplied workbook).

## Install and run (Windows PowerShell)

Python 3.11-3.14 is recommended. This workspace includes a tested Python 3.14 environment in the parent directory.

```powershell
cd 'C:\Users\s.gaybullayev\Downloads\Telegram Desktop\UEFA 2015-2026\UEFA 2015-2026'
.\.venv\Scripts\Activate.ps1
cd ucl_prediction_center
uv pip install --python ..\.venv\Scripts\python.exe -r requirements.txt
python main.py --dry-run
python -m unittest discover -s tests -v
python main.py
```

The existing environment was installed with uv, so `uv pip install --python ..\.venv\Scripts\python.exe -r requirements.txt` is also supported. It does not require pip inside the venv. Without activation run `..\.venv\Scripts\python.exe -B main.py` from this directory.

Close the workbook in Excel before updating it. The script builds and verifies the updated workbook in memory, then writes to the existing source file. No backup, predictions_ready, or pending workbook files are created. If Excel locks the original, the command reports an error without saving another copy; close Excel and rerun. A source hash rejects concurrent edits before writing. Write errors trigger restoration from the original bytes held in memory; an interrupted process or power loss during the write cannot be recovered automatically. Reports and the model use their existing fixed filenames. The Excel table name and original A:P columns remain intact. Custom columns are preserved; old formulas in derived model-output columns are archived in the workbook audit, then replaced by externally trained values. Their obsolete calculated-column rules and calculation-chain entries are removed. Formulas in identifying/custom columns remain protected.

Optional: `python main.py --workbook 'C:\path\source.xlsx' --timezone UTC`. Naive source times are UTC, confirmed by the owner; all output timestamps are UTC stored as Excel datetimes. No separate CSV input is used.

## Data rules and features

`reports/data_validation.json` records every row disposition and every warning/rejection with its Excel row and ID. All sheets and dtypes are inspected in the audit. Matches alone supply results; predictions, champions, team trophy totals, unversioned players, and goal event tables are excluded from training. Original names remain in output; aliases are used only internally. Team logo URLs are copied from `teams.TEAM_URL`, and missing entries are flagged. URLs are not fetched or validated online.

Missing identifiers, dates, teams, same-team matches, negative/non-integer/non-numeric scores, duplicate IDs/fixtures and blocked statuses are rejected explicitly. All duplicate copies are rejected rather than picking one silently. Postponed fixtures are excluded until rescheduled and status is updated. Missing status falls back to valid score pairs and a kickoff at least three hours before cutoff; this limitation is reported. A known scheduled/in-progress status never trains. Future scored rows never train and are flagged. Excel 1900 serial dates and explicit timezone offsets are supported; the supplied workbook uses the 1900 date system. Alternate date systems must be converted first.

Features cover last-5 and last-10 form, scoring/conceding, historical home/away venue performance, online Elo, home advantage, UCL rest days, stage indicators, head-to-head, match experience and current-season form. Final is treated as neutral when no explicit neutral flag exists. Missing seasons remain missing; no season is invented. Season is used for within-season form; a numeric season trend is deliberately omitted. Team rates use five pseudo-matches from prior observed league rates. Replay begins with a weak symmetric 1.35-goal prior, explicitly a model assumption. No observed statistics are replaced with zeros; zero counts indicate genuinely absent recorded history. Rest-day missing values are imputed inside each fitted training pipeline.

## Models and evaluation

Historical class frequencies, dynamic Elo with fitted Davidson draw probabilities, two regularized Poisson goal regressions, logistic regression and histogram gradient boosting are compared. Boosting random early stopping is disabled. Initial training uses the first half of unique kickoff groups; three expanding validation windows cover 50-60%, 60-70%, 70-80%; the final 20% is held out. A result becomes available at kickoff + 3 hours. Fold training excludes results not available at its boundary; online evaluation features advance only using results available at each individual kickoff, as in repeated operational predictions. No fixtures at the same kickoff see one another's scores.

The lowest pooled validation log loss wins; exact ties use calibration error, variation across folds, goal MAE and simplicity. Held-out test metrics never select the model. All five model test scores are reported for audit after selection. No arbitrary ensemble weights or random train/test splits are used. Independent Poisson is used; Dixon-Coles is not introduced without demonstrated benefit. Small datasets use a clearly flagged baseline or unavailable status; fewer than 100 training matches produces no numerical forecast.

`models/ucl_model.joblib` stores the fitted bundle, feature state, columns, cutoff and audit. Load artifacts only from trusted sources. Training lives in `ml_model.py`/`backtesting.py`; `prediction_engine.py` consumes an already fitted model and performs no training. The CLI retrains deliberately to reproduce current validation.

`reports/model_report.md` and `reports/backtest_metrics.json` contain actual validation/test metrics: log loss, multiclass Brier (sum across H/D/A), accuracy, classwise calibration error, confusion matrices (H/D/A), class precision, goal MAE and exact-score top-1/top-3 accuracy. Goal and score metrics are evaluated on each candidate's final joint distribution. `reports/calibration.png` plots the selected model's held-out reliability. Missing metrics remain absent, not fabricated.

## Exact scores, confidence and Excel output

For home rate lambda_h and away rate lambda_a, the base score probability is `exp(-lambda_h) lambda_h^x / x! - exp(-lambda_a) lambda_a^y / y!`. The 11 by 11 matrix for scores 0..10 is normalized. If a different model wins, each H/D/A region is rescaled to its outcome probability, preserving relative Poisson score likelihoods within that region. This is coherent reconciliation, not a fitted blend. Consequently all reported win/draw/loss probabilities, expected goals, top-five scorelines, BTTS, over/under totals and clean sheets come from one final matrix. Score ties sort deterministically. Predictions beyond ten goals are omitted; goal regression rates are bounded at 0.05..6 to limit extrapolation. This is a limitation, not a claim that larger scores cannot occur.

Probabilities are Excel numeric decimals 0..1. A:P retain the existing columns. Additional fields include exact-score/top-five probabilities, goal markets, confidence, coverage, creation timestamp, MODEL_STATUS, original team logos, full matrix JSON and confidence components. `model_audit` stores the feature list, source schema, time cutoff, counts, warnings, selection reason and actual metrics. The existing `Predictions` table expands to include these fields. Source worksheet XML, logo links, comments and other Excel assets are kept unchanged; only predictions/audit/table package parts are edited. The writer uses openpyxl for reading and staged verification and direct OOXML editing for preservation, because openpyxl cannot retain all Excel extensions when saving an existing workbook: https://openpyxl.readthedocs.io/en/3.1.0/tutorial.html

READY requires at least five previous recorded matches for each team and completed validation; coverage becomes HIGH at twenty. New known teams receive league priors with LOW_DATA. Unknown catalog teams receive UNKNOWN_TEAM with blank numeric predictions. MODEL_CONFIDENCE is an equal-component heuristic using history coverage, outcome separation, model agreement, validation calibration and feature completeness, multiplied by history coverage. It is not probability of correctness. Confidence for new teams is zero and its components are exported.

## Power BI integration

1. Run the external model and save/close Excel.
2. In the existing Power BI query, keep using the Excel `Predictions` table. Refresh preview and update any fixed `Changed Type`/`Select Columns` steps to include the new fields. Do not replace the source with a CSV.
3. Add EXACT_SCORE_PROB, MODEL_CONFIDENCE and MODEL_STATUS alongside the existing fields. Use Decimal Number for probabilities/goals and Date/Time for DATE_TIME. Use Whole Number for predicted goals. Include MATCH_ID and set numeric fields to **Don't summarize** in the Python visual.
4. Refresh Power BI Desktop. Configure its Python scripting interpreter to the project environment where pandas and matplotlib and Pillow are installed.
5. Paste `power_bi_visual.py` into the Python visual and supply MATCH_ID, DATE_TIME, HOME_TEAM, AWAY_TEAM, HOME_WIN_PROB, DRAW_PROB, AWAY_WIN_PROB, PREDICTED_HOME_GOALS, PREDICTED_AWAY_GOALS, EXACT_SCORE_PROB, EXPECTED_HOME_GOALS, EXPECTED_AWAY_GOALS, MODEL_CONFIDENCE and MODEL_STATUS (or PREDICTION_STATUS). Also add HOME_LOGO_URL and AWAY_LOGO_URL, or HOME_TEAM_LOGO and AWAY_TEAM_LOGO. Both header pairs are supported; blank values fall back to the other pair and local photo files.

The visual only renders the supplied `dataset`. It displays valid numerical values, including estimates marked LOW_DATA, with status visible; it uses N/A for absent forecasts. It does not train, read Excel or load joblib artifacts. It draws badge images next to both teams, first from embedded image/base64 columns, then from the configured local photo directory, then from supplied HTTP(S) URLs in Desktop. Existing Manchester City raster artwork is used instead of its SVG URL. Missing or corrupt images leave team names and predictions visible; the footer identifies unavailable logos. Python visuals can collapse duplicate rows, hence MATCH_ID must be included. A service refresh requires a separately configured gateway/runtime. The existing `.pbix` is not rewritten automatically; existing Power Query and visual configuration must be reviewed in Power BI.

## Known limits

The model trusts workbook results/fixtures and does not authenticate them externally. Some future-looking summary sheets in the workbook are intentionally excluded. UCL-only history is sparse for newcomers and misses domestic games, injuries, lineups, travel and true rest. Without completion timestamps a three-hour availability lag is conservative but cannot identify every delayed or abandoned match. Scores may include extra time; no regulation-only guarantee is possible. Neutral venues are inferred only for finals unless a neutral flag exists. Season aggregates and team titles are never taken from final standings. Backtest sample size is modest and calibration varies by period. Forecasts are statistical estimates; exact scores are never guaranteed.


## Team logos in the Python visual

Replace the old code in the Power BI Python visual with the ENTIRE updated power_bi_visual.py file. A local source-file edit does not automatically replace a script already pasted into a PBIX. Add HOME_LOGO_URL / AWAY_LOGO_URL or HOME_TEAM_LOGO / AWAY_TEAM_LOGO to the visual Values. Keep MATCH_ID and use Don't summarize. Set LOGO_DIRECTORY near the start of the script if the project is moved or used on another computer. Pillow is now a direct dependency.

The script supports existing PNG/JPEG/WebP images. SVG URLs require an existing raster counterpart; the supplied photo directory contains Manchester City's PNG counterpart. Missing badges are explicitly listed in the visual footer and are never replaced with a fabricated club badge.

Power BI Service blocks network access and does not have this computer's photo folder. For published reports, provide raster data URIs or raw base64 as HOME_LOGO_BASE64 and AWAY_LOGO_BASE64 fields in the visual dataset; those take priority and require neither URL access nor local files. See Microsoft's documented network restriction: https://learn.microsoft.com/en-us/power-bi/connect-data/service-python-packages-support
