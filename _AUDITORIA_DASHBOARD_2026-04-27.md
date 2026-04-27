# Auditoría Dashboard FEAB — 2026-04-27

**Generado**: 2026-04-27T06:32:42.447605Z → 2026-04-27T06:32:44.495844Z
**Modo**: LIVE Socrata

## Sumario

- Items en watch list: **491**
- Portal cache entries: 158
- jbjy-vk9h LIVE rows: 288
- rpmr-utcd LIVE rows: 382
- rpmr orphan (SECOP I legacy, fuera del watch): 88

## Cobertura

| Cobertura | Items | % |
|---|---:|---:|
| `api` | 6 | 1.2 % |
| `integrado` | 158 | 32.2 % |
| `portal` | 0 | 0.0 % |
| `none` | 327 | 66.6 % |

## Severidad de issues

| Severidad | Count | Significado |
|---|---:|---|
| scrape | 319 | 📥 Scrape candidate — necesita portal scrape |

## FP detectados (cardinal — bloquea deploy)

✅ **0 FP** — la cascada `api > integrado > portal > none` se respeta para los 491 items.

## FN detectados (cardinal — bloquea deploy)

✅ **0 FN** — ningún item con `coverage=none` tiene su dato en alguna de las 3 fuentes API.

## Candidatos para scrape del portal community.secop

**319 procesos** PPI sin `notice_uid` resuelto y sin match en ninguna fuente API. Para que el dashboard sea espejo completo de los 491 links (regla cardinal del usuario), estos necesitan que `scripts/scrape_portal.py` los procese contra community.secop con captcha solver Whisper.

Sample (primeros 10):
- `CO1.PPI.38453188` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.36786565` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.39768065` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.39464215` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.NTC.5405127` · sheets=['FEAB 2024'] · vigencias=['2024']
- `CO1.NTC.5405232` · sheets=['FEAB 2024'] · vigencias=['2024']
- `CO1.NTC.5419109` · sheets=['FEAB 2024'] · vigencias=['2024']
- `CO1.NTC.5578040` · sheets=['FEAB 2024'] · vigencias=['2024']
- `CO1.NTC.5578203` · sheets=['FEAB 2024'] · vigencias=['2024']
- `CO1.NTC.5578214` · sheets=['FEAB 2024'] · vigencias=['2024']

## Verdict

✅ **TODO LIMPIO** — 0 FP, 0 FN. Cascada cardinal respetada.

Sample manual de la Dra sigue siendo obligatorio (CLAUDE.md sección 'Smoke test canónico'). Esta auditoría es PRE-condición, no reemplazo.