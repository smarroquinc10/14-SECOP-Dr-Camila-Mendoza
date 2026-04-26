# Auditoría Dashboard FEAB — 2026-04-26

**Generado**: 2026-04-26T10:02:27.181492Z → 2026-04-26T10:02:28.710286Z
**Modo**: LIVE Socrata

## Sumario

- Items en watch list: **491**
- Portal cache entries: 66
- jbjy-vk9h LIVE rows: 288
- rpmr-utcd LIVE rows: 382
- rpmr orphan (SECOP I legacy, fuera del watch): 88

## Cobertura

| Cobertura | Items | % |
|---|---:|---:|
| `api` | 6 | 1.2 % |
| `integrado` | 158 | 32.2 % |
| `portal` | 54 | 11.0 % |
| `none` | 273 | 55.6 % |

## Severidad de issues

| Severidad | Count | Significado |
|---|---:|---|
| scrape | 265 | 📥 Scrape candidate — necesita portal scrape |

## FP detectados (cardinal — bloquea deploy)

✅ **0 FP** — la cascada `api > integrado > portal > none` se respeta para los 491 items.

## FN detectados (cardinal — bloquea deploy)

✅ **0 FN** — ningún item con `coverage=none` tiene su dato en alguna de las 3 fuentes API.

## Candidatos para scrape del portal community.secop

**265 procesos** PPI sin `notice_uid` resuelto y sin match en ninguna fuente API. Para que el dashboard sea espejo completo de los 491 links (regla cardinal del usuario), estos necesitan que `scripts/scrape_portal.py` los procese contra community.secop con captcha solver Whisper.

Sample (primeros 10):
- `CO1.PPI.38453188` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.36786565` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.39768065` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.39464215` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.22985876` · sheets=['FEAB 2023'] · vigencias=['2023']
- `CO1.PPI.23358296` · sheets=['FEAB 2023'] · vigencias=['2023']
- `CO1.PPI.23858655` · sheets=['FEAB 2023'] · vigencias=['2023']
- `CO1.PPI.24316630` · sheets=['FEAB 2023'] · vigencias=['2023']
- `CO1.PPI.25243670` · sheets=['FEAB 2023'] · vigencias=['2023']
- `CO1.PPI.25261639` · sheets=['FEAB 2023'] · vigencias=['2023']

## Verdict

✅ **TODO LIMPIO** — 0 FP, 0 FN. Cascada cardinal respetada.

Sample manual de la Dra sigue siendo obligatorio (CLAUDE.md sección 'Smoke test canónico'). Esta auditoría es PRE-condición, no reemplazo.