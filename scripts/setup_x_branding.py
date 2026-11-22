#!/usr/bin/env python3
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
storage_file = BASE_DIR / "assets" / ".browser_profiles" / "x_storage_state.json"
avatar_path = BASE_DIR / "assets" / "avatar.jpg"
banner_path = BASE_DIR / "assets" / "banner_extra.jpg"

new_name = "GTA VI Hub Extra"
new_bio = (
    "Guías diarias de GTA 6 en español 🎯\n"
    "💰 Dinero rápido • 🚗 Coches gratis • 🔫 Armas ocultas • 📍 Localizaciones en Leonida\n"
    "Menos buscar, más jugar 👇"
)
new_location = "Vice City, Leonida"
new_url = "https://youtube.com/@gtavihubextra"

print("=" * 60)
print(" SETUP PERFIL X — GTA VI Hub Extra")
print("=" * 60)
print(f"[*] Avatar: {avatar_path} (Existe: {avatar_path.exists()})")
print(f"[*] Banner: {banner_path} (Existe: {banner_path.exists()})")

with sync_playwright() as p:
    b = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    )
    ctx = b.new_context(
        storage_state=str(storage_file),
        locale="es-ES",
        viewport={"width": 1400, "height": 1200}
    )
    page = ctx.new_page()
    print("[*] Abriendo configuración de perfil en X...")
    page.goto("https://x.com/settings/profile", wait_until="networkidle", timeout=35000)
    page.wait_for_timeout(3000)

    # Actualizar campos de texto en el formulario
    js_update = """
    ({name, bio, location, url}) => {
        function setReactValue(el, val) {
            const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
            const nativeSet = Object.getOwnPropertyDescriptor(proto, 'value').set;
            nativeSet.call(el, val);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }

        const nameInp = document.querySelector('input[name="displayName"]');
        if (nameInp) setReactValue(nameInp, name);

        const bioInp = document.querySelector('textarea[name="description"]');
        if (bioInp) setReactValue(bioInp, bio);

        const locInp = document.querySelector('input[name="location"]');
        if (locInp) setReactValue(locInp, location);

        const urlInp = document.querySelector('input[name="url"]');
        if (urlInp) setReactValue(urlInp, url);

        return {
            name: nameInp ? nameInp.value : null,
            bio: bioInp ? bioInp.value : null,
            loc: locInp ? locInp.value : null,
            url: urlInp ? urlInp.value : null
        };
    }
    """
    res = page.evaluate(js_update, {"name": new_name, "bio": new_bio, "location": new_location, "url": new_url})
    print(f"[✓] Inputs actualizados: {res}")
    page.wait_for_timeout(2000)

    # Subir imágenes
    file_inputs = page.locator('input[type="file"]').all()
    print(f"[*] Inputs de archivo: {len(file_inputs)}")
    if len(file_inputs) >= 2:
        try:
            print("[*] Subiendo banner...")
            file_inputs[0].set_input_files(str(banner_path))
            page.wait_for_timeout(3000)
            apply = page.locator('[data-testid="applyButton"]')
            if apply.count() > 0:
                page.evaluate('() => { const b = document.querySelector(\'[data-testid="applyButton"]\'); if (b) b.click(); }')
                print("    [✓] Banner aplicado")
                page.wait_for_timeout(2000)
        except Exception as e:
            print(f"    [!] Error banner: {e}")

        try:
            print("[*] Subiendo avatar...")
            file_inputs[1].set_input_files(str(avatar_path))
            page.wait_for_timeout(3000)
            apply = page.locator('[data-testid="applyButton"]')
            if apply.count() > 0:
                page.evaluate('() => { const b = document.querySelector(\'[data-testid="applyButton"]\'); if (b) b.click(); }')
                print("    [✓] Avatar aplicado")
                page.wait_for_timeout(2000)
        except Exception as e:
            print(f"    [!] Error avatar: {e}")

    page.wait_for_timeout(2000)
    save_btn = page.locator('[data-testid="Profile_Save_Button"]')
    print(f"[*] Botón guardar visible: {save_btn.count() > 0}")

    if save_btn.count() > 0:
        page.evaluate('() => { const b = document.querySelector(\'[data-testid="Profile_Save_Button"]\'); if (b) b.click(); }')
        page.wait_for_timeout(7000)
        print("[✓] ¡Perfil guardado en X con éxito!")

    ctx.storage_state(path=str(storage_file))
    print("[✓] Sesión storage_state guardada.")
    b.close()
