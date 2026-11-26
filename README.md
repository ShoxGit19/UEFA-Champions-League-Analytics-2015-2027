# UEFA Champions League Analytics (2015–2027)

UEFA Champions League ma’lumotlari, Power BI dashboard’i va tashqi prediction pipeline’i.

## Tarkib

- `UEFA.pbix` — Power BI dashboard.
- `UEFA Champions League 2015-2027.xlsx` — asosiy Excel workbook; 11 ta sheet mavjud.
- `ucl_prediction_center/` — matchlarni tekshiruvchi, model tanlovini bajaruvchi va prediction’larni Excel’ga yozuvchi Python pipeline.
- `internet_qidiruv_promptlari.txt` — Matchday bo‘yicha internetdan ma’lumot qidirish va bazaga xavfsiz saqlash promptlari.
- `photo/` — dashboard rasmlari va logotiplari.

## Excel jadvallari

`SeasonWinners`, `FinalMatchTeam`, `FinalMatchPlayer`, `Teams`, `Stadiums`, `Players`, `Matches`, `Managers`, `Goals`, `BracketProgression` va `Predictions`.

## Prediction pipeline’ni ishga tushirish

Windows PowerShell:

```powershell
cd ucl_prediction_center
..\.venv\Scripts\python.exe -B main.py
```

Dry run uchun:

```powershell
..\.venv\Scripts\python.exe -B main.py --dry-run
```

Pipeline valid historical matchlardan model yaratadi va workbook’dagi `Predictions` sheet’ni yangilaydi.

## PostgreSQL / Neon

Database connection string’ni source code’ga yozmang. Environment variable ishlating:

```powershell
$env:UEFA_DB_URL = "postgresql://..."
```

Ma’lumotlar `public` schema’dagi `matches`, `players`, `goals`, `teams`, `stadiums`, `managers`, `season_winners`, `final_match_team`, `final_match_player`, `bracket_progression` va `predictions` jadvallarida saqlanadi. Yangilash transaction, validation va UPSERT orqali bajarilishi kerak; `neon_auth` schema’iga tegilmaydi.

## Railway worker

Railway worker yangi Matchday ma’lumotlarini oladi, source URL va raw payload’ni audit qiladi, validation va duplicate tekshiruvdan o‘tkazadi, PostgreSQL’ga transaction ichida UPSERT qiladi va commit’dan keyin prediction pipeline’ni ishga tushiradi.

Railway build uchun repository root’ida `requirements.txt` va `railway.toml` mavjud. Service Settings’da Root Directory bo‘sh yoki `/` bo‘lishi kerak. Start command `python railway_worker.py` orqali har `SYNC_INTERVAL_MINUTES` da prediction worker ishga tushadi.

Railway Variables:

```env
DATABASE_URL=postgresql://...
UEFA_DB_URL=postgresql://...
OPENAI_API_KEY=...
SEARCH_PROVIDER_KEY=...
SYNC_INTERVAL_MINUTES=5
```

Secret’larni GitHub’ga commit qilmang.

## Ishonchlilik

UEFA rasmiy sahifasi birinchi manba sifatida tekshiriladi. Topilmagan yoki qarama-qarshi ma’lumotlar taxmin qilinmaydi; `UNKNOWN`, `null` yoki `pending_review` holatida qoldiriladi. Score va goal eventlar mosligi tekshirilmasdan prediction yangilanmaydi.

## Litsenziya va media

Dashboard va rasmlardan foydalanishda asl manba hamda tegishli foydalanish shartlarini tekshiring.
