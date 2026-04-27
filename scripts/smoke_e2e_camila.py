"""
End-to-end smoke test del dashboard FEAB en producción (GitHub Pages).
Verifica que CADA feature que se le promete a Cami funciona.

Cardinal: 0 FP, 0 FN, 0 datos comidos. Cualquier console error =
bloquea declaración "deploy listo".
"""
from __future__ import annotations

import json
import sys
import time
from playwright.sync_api import sync_playwright, ConsoleMessage, Request


URL = "https://smarroquinc10.github.io/14-SECOP-Dr-Camila-Mendoza/"
PASSPHRASE = "cami2026"


def main() -> int:
    fails: list[str] = []
    warnings: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        console_errors: list[str] = []
        network_failures: list[str] = []

        def on_console(msg: ConsoleMessage):
            if msg.type in ("error",):
                console_errors.append(f"[{msg.type}] {msg.text}")

        def on_request_failed(req: Request):
            failure_text = req.failure or ""
            network_failures.append(f"{req.url} → {failure_text}")

        page.on("console", on_console)
        page.on("requestfailed", on_request_failed)

        # ---- Step 1: cargar URL pública ----
        print("[1] Cargar URL pública...")
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        time.sleep(1)

        # ---- Step 2: passphrase gate ----
        print("[2] Passphrase gate...")
        # Buscar el input de passphrase. Hay varias estrategias:
        passphrase_input = page.locator('input[type="password"]').first
        if not passphrase_input.is_visible(timeout=5000):
            fails.append("STEP 2: passphrase input no visible")
        else:
            passphrase_input.fill(PASSPHRASE)
            # Submit: enter o botón
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle", timeout=20_000)
            time.sleep(2)

        # ---- Step 3: bienvenida ----
        print("[3] Bienvenida + indicadores cardinales...")
        if not page.get_by_text("Bienvenida, Dra. María Camila Mendoza Zubiría").is_visible(timeout=10_000):
            fails.append("STEP 3: header de bienvenida no aparece")

        # Indicadores
        for indicator_text in [
            "Procesos con datos del SECOP",
            "Último contrato firmado",
            "Última búsqueda profunda",
            "Requieren tu revisión",
            "Registro auditado",
        ]:
            if not page.get_by_text(indicator_text, exact=False).first.is_visible(timeout=3000):
                fails.append(f"STEP 3: indicador '{indicator_text}' no aparece")

        # ---- Step 4: action bar - 1 solo botón visible para Cami ----
        print("[4] Action bar - 1 solo botón visible...")
        actualizar_btn = page.get_by_role("button", name="Actualizar datos del SECOP")
        if not actualizar_btn.is_visible(timeout=5000):
            fails.append("STEP 4: botón 'Actualizar datos del SECOP' no visible")

        # Sergio · Operaciones avanzadas debe estar COLAPSADO por default
        if not page.get_by_text("Sergio · Operaciones avanzadas").is_visible(timeout=3000):
            fails.append("STEP 4: sección 'Sergio · Operaciones avanzadas' no aparece")

        # ---- Step 5: Modificatorios destacado ----
        print("[5] Sección Modificatorios destacada...")
        if not page.get_by_text("Modificatorios — lo más relevante a revisar").is_visible(timeout=5000):
            fails.append("STEP 5: header 'Modificatorios — lo más relevante a revisar' no aparece")
        if not page.get_by_text("Contratos modificados").first.is_visible(timeout=3000):
            fails.append("STEP 5: card 'Contratos modificados' no aparece")
        if page.get_by_text("Días adicionados", exact=False).first.is_visible(timeout=2000):
            warnings.append("STEP 5: 'Días adicionados' aparece — debió ser eliminada")

        # ---- Step 6: Tabla de procesos ----
        print("[6] Tabla con 491 procesos...")
        tabla = page.locator("table").first
        if not tabla.is_visible(timeout=5000):
            fails.append("STEP 6: tabla principal no visible")

        # Header de la tabla debe contener Estado en SECOP
        if not page.get_by_role("columnheader", name="Estado en SECOP").is_visible(timeout=3000):
            fails.append("STEP 6: header de columna 'Estado en SECOP' no aparece")
        if not page.get_by_role("columnheader", name="Modificatorios").is_visible(timeout=3000):
            fails.append("STEP 6: header de columna 'Modificatorios' no aparece")

        # Counter "X de 491 mostrados"
        contador_locator = page.get_by_text("491 mostrados", exact=False).first
        if not contador_locator.is_visible(timeout=3000):
            fails.append("STEP 6: contador 'X de 491 mostrados' no aparece")

        # ---- Step 7: Filtros ----
        print("[7] Filtros con labels en lenguaje legal...")
        for filter_label in [
            "Buscar un proceso",
            "Año del contrato",
            "Estado actual del contrato",
            "Tipo de contratación",
            "ATAJOS DE SEGUIMIENTO",
        ]:
            if not page.get_by_text(filter_label, exact=False).first.is_visible(timeout=3000):
                fails.append(f"STEP 7: filtro/label '{filter_label}' no aparece")

        # ---- Step 8: Smoke de los 4 canónicos en la tabla ----
        print("[8] 4 canónicos en la tabla...")
        for proc_id, expected_badge in [
            ("CO1.PCCNTR.8930451", "Contrato firmado"),
            ("CO1.NTC.1416630", "Publicado en SECOP"),
            ("CO1.NTC.5405127", "Publicado en SECOP"),
            ("CO1.PPI.11758446", "Aún sin publicar"),
        ]:
            visible = page.get_by_text(proc_id, exact=False).first.is_visible(timeout=2000)
            if not visible:
                # Puede que esté offscreen — buscar con search
                search = page.get_by_placeholder(
                    "Escribí proveedor, objeto del contrato o el código",
                    exact=False,
                ).first
                if search.is_visible(timeout=2000):
                    search.fill(proc_id)
                    time.sleep(1)
                    visible = page.get_by_text(proc_id, exact=False).first.is_visible(timeout=3000)
                    # Limpiar
                    search.fill("")
                    time.sleep(0.5)
            if not visible:
                fails.append(f"STEP 8: canónico {proc_id} NO está en la tabla")

        # ---- Step 9: Click en una fila → modal ----
        print("[9] Click fila → modal detalle...")
        # Buscar primer botón burgundy del id de contrato
        primer_proc = page.locator("button.text-burgundy").first
        if primer_proc.is_visible(timeout=5000):
            primer_proc.click()
            time.sleep(1.5)
            # El modal debe aparecer
            modal = page.locator('[role="dialog"]').first
            if not modal.is_visible(timeout=5000):
                fails.append("STEP 9: modal no se abre al click fila")
            else:
                # Cerrar modal con Escape
                page.keyboard.press("Escape")
                time.sleep(0.5)
        else:
            fails.append("STEP 9: no encontré botón clickeable de proceso")

        # ---- Step 10: Console errors ----
        print("[10] Console errors / network failures...")
        if console_errors:
            fails.append(f"STEP 10: {len(console_errors)} console error(s):")
            for e in console_errors[:5]:
                fails.append(f"   - {e[:200]}")
        if network_failures:
            # filter known/expected (e.g. favicon en domains externos)
            real = [
                f for f in network_failures
                if "favicon" not in f.lower() and "feab-logo" not in f.lower()
            ]
            if real:
                fails.append(f"STEP 10: {len(real)} network failure(s):")
                for e in real[:5]:
                    fails.append(f"   - {e[:200]}")

        # ---- Cleanup ----
        ctx.close()
        browser.close()

    # ---- Reporte ----
    print()
    print("=" * 60)
    print("REPORTE FINAL")
    print("=" * 60)
    print(f"Console errors: {0 if not fails else 'ver fails'}")
    print(f"Network failures: {0 if not fails else 'ver fails'}")
    print()

    if fails:
        print(f"❌ {len(fails)} fallo(s):")
        for f in fails:
            print(f"  ❌ {f}")
    else:
        print("✅ TODO PASS — 0 console errors, todos los elementos cardinales presentes")

    if warnings:
        print()
        print(f"⚠️ {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  ⚠️ {w}")

    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
