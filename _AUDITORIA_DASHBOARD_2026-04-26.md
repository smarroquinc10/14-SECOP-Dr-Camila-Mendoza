# Auditoría Dashboard FEAB — 2026-04-26

**Generado**: 2026-04-26T23:10:29.670986Z → 2026-04-26T23:10:31.448049Z
**Modo**: LIVE Socrata

## Sumario

- Items en watch list: **491**
- Portal cache entries: 473
- jbjy-vk9h LIVE rows: 288
- rpmr-utcd LIVE rows: 382
- rpmr orphan (SECOP I legacy, fuera del watch): 88

## Cobertura

| Cobertura | Items | % |
|---|---:|---:|
| `api` | 6 | 1.2 % |
| `integrado` | 158 | 32.2 % |
| `portal` | 316 | 64.4 % |
| `none` | 11 | 2.2 % |

## Severidad de issues

| Severidad | Count | Significado |
|---|---:|---|
| scrape | 3 | 📥 Scrape candidate — necesita portal scrape |

## FP detectados (cardinal — bloquea deploy)

✅ **0 FP** — la cascada `api > integrado > portal > none` se respeta para los 491 items.

## FN detectados (cardinal — bloquea deploy)

✅ **0 FN** — ningún item con `coverage=none` tiene su dato en alguna de las 3 fuentes API.

## Candidatos para scrape del portal community.secop

**3 procesos** PPI sin `notice_uid` resuelto y sin match en ninguna fuente API. Para que el dashboard sea espejo completo de los 491 links (regla cardinal del usuario), estos necesitan que `scripts/scrape_portal.py` los procese contra community.secop con captcha solver Whisper.

Sample (primeros 10):
- `CO1.PPI.36786565` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.39464215` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.11758446` · sheets=['FEAB 2018-2021'] · vigencias=['2021']

## Verdict

✅ **TODO LIMPIO** — 0 FP, 0 FN. Cascada cardinal respetada.

Sample manual de la Dra sigue siendo obligatorio (CLAUDE.md sección 'Smoke test canónico'). Esta auditoría es PRE-condición, no reemplazo.