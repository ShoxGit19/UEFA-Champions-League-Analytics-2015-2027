# UEFA Champions League Analytics Dashboard (2015–2026)

![UEFA Champions League](photo/UEFA-Champions-League-logo-titule.png)

UEFA Champions League bo‘yicha 2015–2016 mavsumidan 2025–2026 mavsumigacha bo‘lgan ma’lumotlarni tahlil qiluvchi interaktiv Power BI dashboard.

Dashboard orqali chempionlar, final natijalari, eng yaxshi to‘purar va assistentlar, jamoalar, stadionlar, gollar statistikasi hamda final tarkiblarini mavsumlar kesimida ko‘rish mumkin.

## Asosiy imkoniyatlar

- Mavsum va turnir bosqichi bo‘yicha interaktiv filtrlash
- Chempion, murabbiy, final natijasi va final stadioni haqida ma’lumot
- Eng yaxshi to‘purar, assistent va darvozabon ko‘rsatkichlari
- Jamoalar, mamlakatlar va UCL sovrinlari bo‘yicha tahlil
- Gollarning turi va urilgan daqiqasi bo‘yicha taqsimoti
- Mavsumlararo o‘zgarishlarni taqqoslash
- Final o‘yinidagi ikki jamoa tarkibini maydon ko‘rinishida chiqarish
- Futbolchilar, murabbiylar, jamoalar va stadionlar rasmlaridan foydalanish

## Dashboard sahifalari

Power BI hisoboti 5 ta sahifadan tashkil topgan:

1. **Umumiy ko‘rsatkichlar** — chempion, murabbiy, final hisobi, stadion, mavsumdagi gollar, GPM, Ballon d'Or, to‘purar, assistent va darvozabon statistikasi.
2. **Jamoa va futbolchilar tahlili** — jamoa, stadion, mamlakat, UCL sovrinlari, eng yaxshi to‘purar va assistentlar.
3. **Gollar tahlili** — o‘ng/chap oyoq, bosh bilan, penalti, avtogol va jarima zarbasidan urilgan gollar; daqiqalar bo‘yicha taqsimot va mavsumlararo o‘zgarish.
4. **Final tarkiblari** — tanlangan mavsum finalidagi uy va mehmon jamoalarining futbolchilari, pozitsiyalari, rasmlari va klub logotiplari.
5. **Darvozabonlar** — mavsumlar bo‘yicha yetakchi darvozabonlarni ko‘rsatish uchun kartalar galereyasi.

## Loyiha tarkibi

```text
UEFA 2015-2026/
├── UEFA.pbix
├── UEFA Champions League 2015-2026 PowerBI.xlsx
├── photo/
│   └── futbolchilar, murabbiylar, klublar va fon rasmlari
└── README.md
```

| Fayl | Tavsif |
|---|---|
| `UEFA.pbix` | Power BI hisoboti, ma’lumotlar modeli, DAX o‘lchovlari va vizualizatsiyalar |
| `UEFA Champions League 2015-2026 PowerBI.xlsx` | Dashboard uchun asosiy Excel ma’lumotlar manbasi |
| `photo/` | 300 dan ortiq lokal rasm va grafik resurslar |

## Dataset tarkibi

Excel faylida 9 ta varaq va jami 9 112 ta ma’lumot qatori mavjud:

| Varaq | Qatorlar | Tavsif |
|---|---:|---|
| `season_winners` | 11 | Har bir mavsum chempioni, final, to‘purar, assistent, murabbiy va darvozabon ma’lumotlari |
| `final_match_team` | 11 | Finalchi jamoalarning pozitsiyalar bo‘yicha tarkib rasmlari |
| `final_match_player` | 264 | Final o‘yinlari futbolchilari va ularning pozitsiyalari |
| `teams` | 97 | Klublar, mamlakatlar, stadionlar va UCL sovrinlari |
| `stadiums` | 121 | Stadion nomi, shahar, mamlakat va sig‘im |
| `players` | 3 145 | Futbolchilar profili, jamoasi, pozitsiyasi va jismoniy ko‘rsatkichlari |
| `managers` | 80 | Murabbiylar, millati, tug‘ilgan sanasi va jamoasi |
| `matches` | 1 303 | O‘yinlar, hisob, sana, bosqich, stadion va tomoshabinlar soni |
| `goals` | 4 080 | Gollar, muallif, assistent, daqiqa va gol turi |

Asosiy bog‘lanish kalitlari:

- `MATCH_ID` — o‘yinlar va gollarni bog‘laydi
- `PLAYER_ID` / `PID` — futbolchilar va gol mualliflarini bog‘laydi
- `SEASON` — barcha mavsumiy jadvallarni filtrlash uchun ishlatiladi
- `TEAM_NAME`, `HOME_TEAM`, `AWAY_TEAM` — jamoalar bilan bog‘lanish uchun ishlatiladi
- `STADIUM` / `NAME` — o‘yin va stadion ma’lumotlarini bog‘laydi

## Ishga tushirish

### Talablar

- Windows
- [Microsoft Power BI Desktop](https://www.microsoft.com/power-platform/products/power-bi/desktop)
- Rasmlarning tashqi URL manbalarini yuklash uchun internet ulanishi

### Qadamlar

1. Repozitoriyni yuklab oling yoki klon qiling.
2. `.pbix`, `.xlsx` va `photo` papkasini bir joyda saqlang.
3. `UEFA.pbix` faylini Power BI Desktop orqali oching.
4. Zarur bo‘lsa, **Home → Refresh** tugmasi orqali ma’lumotlarni yangilang.
5. Excel manbasi topilmasa, **File → Options and settings → Data source settings** orqali `UEFA Champions League 2015-2026 PowerBI.xlsx` faylining joriy manzilini ko‘rsating.

Hisobot ichida mavsum va turnir bosqichi slicerlaridan foydalanib vizuallarni filtrlash mumkin.

## Ma’lumotlarni yangilash

1. Kerakli Excel varag‘iga yangi ma’lumotlarni kiriting.
2. Mavjud varaq va ustun nomlarini o‘zgartirmang.
3. Kerak bo‘lsa, rasm URL manzillarini yoki `photo/` ichidagi fayllarni yangilang.
4. Power BI Desktop’da hisobotni ochib **Refresh** qiling.
5. Vizualizatsiyalar va mavsum filtrlarini tekshirib, `.pbix` faylini saqlang.

`FINAL_STADUIM_CITY`, `GOAL_KEAPER`, `SEYF` va `Column1` kabi mavjud texnik ustun nomlari Power Query yoki DAX formulalarida ishlatilishi mumkin. Ularni qayta nomlashdan oldin modeldagi bog‘liqliklarni ham yangilash kerak.

## Vizual komponentlar

Hisobot standart Power BI vizuallaridan tashqari xarita, HTML content, multi-line chart, line/bubble chart va tree chart kabi paketga biriktirilgan custom vizuallarni ham o‘z ichiga oladi. Power BI Desktop ularni ishga tushirish uchun ruxsat so‘rashi mumkin.

## Muallif

Dashboard ichidagi muallif identifikatori: **ShoxGit19**

- **Email:** [shohjahon1922@gmail.com](mailto:shohjahon1922@gmail.com)
- **Telegram:** [@gaybullayeev19](https://t.me/gaybullayeev19)
- **LinkedIn:** [Shohjahon G‘aybullayev](https://www.linkedin.com/in/shohjahon-g-aybullayev-b93765299/)
- **Loyiha posti:** [Power BI Sports Analytics](https://www.linkedin.com/posts/shohjahon-g-aybullayev-b93765299_powerbi-sportsanalytics-datavisualization-ugcPost-7472881878073720832-auJo/)

## Litsenziya va media

Loyihada alohida litsenziya fayli mavjud emas. `photo/` papkasidagi va tashqi URL orqali olinadigan media fayllardan foydalanishda ularning asl mualliflik huquqi va foydalanish shartlarini tekshiring.
