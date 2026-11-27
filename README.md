# UEFA Champions League Analytics 2015–2027

Power BI dashboard, Neon PostgreSQL data model and Railway prediction worker for UEFA Champions League analysis.

## Project structure

- `UEFA.pbix` — Power BI report and dashboard.
- `UEFA Champions League 2015-2027.xlsx` — source workbook.
- `ucl_prediction_center/` — training, validation, prediction and Excel writer pipeline.
- `railway_worker.py` — scheduled worker with health-check, retry and notifications.
- `dax/` — final Power BI HTML/DAX measures.
- `internet_qidiruv_promptlari.txt` — controlled source-enrichment prompts.

## Data model

The workbook and Neon database use `Matches`, `Goals`, `Players`, `Teams`, `Managers`, `Stadiums`, `SeasonWinners`, `BracketProgression`, `FinalMatchTeam`, `FinalMatchPlayer` and `Predictions`.

The public PostgreSQL schema is the application data boundary. Prediction output is written to `public.predictions`; authentication schemas are never modified by the pipeline.

## Prediction metadata

Each prediction includes:

- `MODEL_VERSION` — reproducible model version.
- `MODEL_CONFIDENCE` — transparent quality heuristic, not a guarantee of correctness.
- `DATA_COVERAGE` — `LOW`, `MEDIUM` or `HIGH`.
- `PREDICTION_CREATED_AT` — UTC creation timestamp.
- `SOURCE_SEASON` — season of the fixture.
- `TRAINING_SAMPLE_COUNT` — historical matches used for training.
- `MODEL_STATUS` and `PREDICTION_STATUS` — operational status.

## Local run

```powershell
cd ucl_prediction_center
..\.venv\Scripts\python.exe -B main.py --dry-run
```

Use `--dry-run` to generate reports and the model artifact without changing the workbook. Close Excel before a real write.

## Railway deployment

Railway starts `python railway_worker.py`. By default the worker runs once per day at **09:00 Asia/Tashkent**, retries failed runs with backoff, emits logs, exposes `/health` and `/healthz` on `PORT`, records the last successful sync and sends optional Telegram/SMTP alerts on startup, success and final failure.

### Railway variables

Required:

```env
DATABASE_URL=postgresql://...
UEFA_DB_URL=postgresql://...
```

Optional:

```env
DAILY_SYNC_HOUR_TASHKENT=9
SYNC_MAX_RETRIES=3
SYNC_RETRY_BACKOFF_SECONDS=30
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_CHAT_ID=...
SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
ALERT_EMAIL_TO=...
LOG_LEVEL=INFO
```

Never commit database URLs, bot tokens or SMTP passwords. Store them only in Railway Variables or a local untracked `.env` file.

## Monitoring

`GET /healthz` returns `status`, `last_success_at`, `last_failure_at`, `last_error`, `last_duration_seconds`, `runs` and `interval_minutes`.

HTTP 200 means the worker is starting or healthy. HTTP 503 means the latest sync exhausted its retry attempts.

## Data quality and safety

The pipeline validates fixture IDs, team names, historical cutoffs, prediction probabilities and score matrices before writing. It uses the existing workbook and preserves non-prediction workbook parts. Unknown or conflicting values are not guessed; they remain unavailable or are reported for review.

## Security

Rotate any database credential exposed outside Railway. Use least-privilege credentials, keep secrets out of Git, and review Railway logs before sharing them publicly.

## License and media

Verify UEFA, club, image and logo licensing terms before publishing or redistributing dashboard assets.
