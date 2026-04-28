# Plan · OCR + clasificación cardinal de modificatorios

**Fecha**: 2026-04-28
**Operador**: Sergio Marroquín Cabrera
**Pedido cardinal Dra**: "un humano se mete a todos los pdfs porque el nombre del documento no es fiable entonces toca entrar al pdf"
**Barra de calidad**: 0 FP · 0 FN · 0 datos comidos (igual que el resto del sistema)

---

## Problema actual

El dashboard cuenta modificatorios usando regex sobre el NOMBRE del PDF.
Cobertura medida sobre 473 procesos · 12,497 docs:

- Regex actual `/modificatorio|otrosí|adendo|adicional al contrato/i`: 129 / 855 = **15 %**.
- 726 docs cardinales perdidos como FN.
- Aún si captura el doc, no clasifica TIPO (Adición vs Prórroga vs Cesión).
- Aún si captura tipo, no extrae NÚMERO ni VALOR ni FECHA del modificatorio.

---

## Approach cardinal de 3 capas independientes

Cada PDF pasa por las 3 capas. Solo se acepta clasificación si al menos 2 coinciden.
Si discrepan → flag "Pendiente revisión humana" + audit trail con detalle.

### Capa 1 · Clasificación por nombre (rápida · ya lista)

`app/src/lib/classify-modificatorios.ts` · regex con 11 tipos + filtros anti-FP.
Cobertura esperada cuando el nombre es claro: ~70 %.

### Capa 2 · Extracción de texto nativo (rápida · pdfplumber)

Para PDFs nativos (no escaneados). 80% de los PDFs del SECOP son nativos.
Extrae las primeras 500-1000 palabras · busca keywords cardinales:

- `MODIFICATORIO N° X AL CONTRATO Y`
- `ADICIÓN No X` / `ADICIONAR EL VALOR`
- `PRÓRROGA del plazo`
- `ACTA DE LIQUIDACIÓN`
- `ACTA DE SUSPENSIÓN`
- `CESIÓN del contrato`
- `TERMINACIÓN ANTICIPADA`
- etc.

### Capa 3 · OCR con consenso (lento · Tesseract + doctr)

Para PDFs escaneados (~20% del total). Doble engine para validación:

- Tesseract con lang=spa + post-processing
- doctr (PyTorch) sobre las primeras 3 páginas
- Si ambos extraen el mismo tipo · alta confianza
- Si discrepan · flag para humano

---

## Datos extraídos por cada modificatorio

```jsonc
{
  "process_id": "CO1.NTC.5405127",
  "pdf_url": "https://community.secop.gov.co/Public/...",
  "pdf_name": "Modificatorio No 2 firmado y fechado.pdf",
  "tipo": "Adición",
  "numero": "2",
  "fecha_documento": "2025-01-27",
  "valor_adicionado": 8000000,
  "dias_prorrogados": 60,
  "objeto_resumen": "Adición de 8 millones por 60 días adicionales",
  "cedente": null,           // solo para tipo=Cesión
  "cesionario": null,        // solo para tipo=Cesión
  "extracted_at": "2026-04-28T...",
  "extraction_method": "pdfplumber",  // o "tesseract", "doctr", "hybrid"
  "confidence": 0.95,         // 0-1
  "text_sample": "...",       // primeros 500 chars del texto extraído
  "tipo_por_nombre": "Modificatorio",  // capa 1
  "tipo_por_contenido": "Adición",     // capa 2 / 3
  "consensus": true,          // capa 1 ∪ capa 2 ∪ capa 3 coinciden
  "needs_human_review": false
}
```

---

## Criterios de aceptación cardinal (0 FP · 0 FN)

### Sample manual de validación pre-deploy

Antes de declarar el feature listo:

1. **Tomar 30 PDFs aleatorios** ya procesados (variando tipos y origen).
2. **Cami abre cada uno manualmente** y confirma:
   - Tipo correcto
   - Número correcto
   - Valor correcto (si aplica)
   - Fecha correcta
3. **Si los 30 dan match exacto** → 0 FP / 0 FN cardinal cumplido.
4. **Si alguno falla** → refinar clasificador + repetir sample con OTROS 30 PDFs.

### Flag automático "Pendiente revisión humana" cuando:

- Las 3 capas discrepan en tipo
- OCR confidence < 0.8
- No se puede extraer número de modificatorio claro
- Texto del PDF es ilegible

### Datos comidos = 0

- Todos los PDFs del seed se procesan (incluso si fallan, queda registro)
- Si un PDF falla descarga · audit trail · NO se cuenta como modificatorio (no inventa)
- Si el clasificador no detecta tipo · queda como "Otro" honesto · NO se descarta

---

## Pasos ejecutables

1. ✅ Plan escrito (este archivo)
2. ⬜ Script Python `scripts/classify_modificatorios_pdf.py` con capa 2 (pdfplumber)
3. ⬜ Piloto con 5 PDFs reales · validación manual antes de seguir
4. ⬜ Capa 3 OCR Tesseract + doctr con consensus
5. ⬜ Procesar los 12,497 PDFs · estimado 1-2h primer corrida
6. ⬜ Sample manual de 30 PDFs · iteración hasta 0 FP/FN
7. ⬜ Persistir `app/public/data/modificatorios_classified.json`
8. ⬜ Frontend: tabla y modal con tipo + número + valor + fecha
9. ⬜ Tests pytest del clasificador · 30+ casos cubiertos
10. ⬜ verify_multilayer extendido con capa nueva "modificatorios clasificados"
11. ⬜ Cron mensual: re-procesa solo PDFs nuevos
12. ⬜ Commit + push + deploy + smoke
13. ⬜ Sample humano de Cami · cierre cardinal

---

## Tiempo honesto

- Script + piloto + validación: **3-4 h**
- Procesamiento de los 12,497 PDFs (background): **1-2 h CPU**
- Iteración sobre FP/FN del sample: **2-3 h**
- Frontend display: **2 h**
- Cron + tests + deploy: **1-2 h**
- **Total**: **~10-12 h reales**

Honesto: no termino hoy en una sola sesión. Avanzo por checkpoints.
Cada checkpoint te muestro resultado · si aprueba, sigo · si no, ajusto.
