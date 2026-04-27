# Auditoría Dashboard FEAB — 2026-04-27

**Generado**: 2026-04-27T10:08:51.059185Z → 2026-04-27T10:10:42.446560Z
**Modo**: LIVE Socrata

## Sumario

- Items en watch list: **491**
- Portal cache entries: 473
- jbjy-vk9h LIVE rows: 0
- rpmr-utcd LIVE rows: 382
- rpmr orphan (SECOP I legacy, fuera del watch): 88

## Cobertura

| Cobertura | Items | % |
|---|---:|---:|
| `api` | 0 | 0.0 % |
| `integrado` | 158 | 32.2 % |
| `portal` | 316 | 64.4 % |
| `none` | 17 | 3.5 % |

## Severidad de issues

| Severidad | Count | Significado |
|---|---:|---|
| scrape | 9 | 📥 Scrape candidate — necesita portal scrape |

## FP detectados (cardinal — bloquea deploy)

✅ **0 FP** — la cascada `api > integrado > portal > none` se respeta para los 491 items.

## FN detectados (cardinal — bloquea deploy)

✅ **0 FN** — ningún item con `coverage=none` tiene su dato en alguna de las 3 fuentes API.

## Candidatos para scrape del portal community.secop

**9 procesos** PPI sin `notice_uid` resuelto y sin match en ninguna fuente API. Para que el dashboard sea espejo completo de los 491 links (regla cardinal del usuario), estos necesitan que `scripts/scrape_portal.py` los procese contra community.secop con captcha solver Whisper.

Sample (primeros 10):
- `CO1.PCCNTR.8930451` · sheets=['FEAB 2026'] · vigencias=['2026']
- `CO1.PCCNTR.8930521` · sheets=['FEAB 2026'] · vigencias=['2026']
- `CO1.PCCNTR.8930513` · sheets=['FEAB 2026'] · vigencias=['2026']
- `CO1.PCCNTR.8930039` · sheets=['FEAB 2026'] · vigencias=['2026']
- `CO1.PCCNTR.8929690` · sheets=['FEAB 2026'] · vigencias=['2026']
- `CO1.PCCNTR.8930109` · sheets=['FEAB 2026'] · vigencias=['2026']
- `CO1.PPI.36786565` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.39464215` · sheets=['FEAB 2025'] · vigencias=['2025']
- `CO1.PPI.11758446` · sheets=['FEAB 2018-2021'] · vigencias=['2021']

## Verdict

✅ **TODO LIMPIO** — 0 FP, 0 FN. Cascada cardinal respetada.

Sample manual de la Dra sigue siendo obligatorio (CLAUDE.md sección 'Smoke test canónico'). Esta auditoría es PRE-condición, no reemplazo.