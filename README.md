# 🎮 GTA VI Hub Spain - Pipeline Autónomo Multiplataforma (M4 Mac)

Sistema de producción y distribución totalmente automatizado para **YouTube Shorts, TikTok e Instagram Reels**, optimizado para ejecutarse silenciosamente en segundo plano en **Apple Silicon (M4)** con aceleración por hardware (`VideoToolbox`).

### 🌐 Redes Sociales y Canales Oficiales:
- 🔴 **YouTube:** [GTA VI Hub Spain](https://www.youtube.com/channel/UCBOl2KuaHEoUWYWJqb7ID9Q)
- 📸 **Instagram:** [@gtavihubspain](https://www.instagram.com/gtavihubspain/)
- 🎵 **TikTok:** [@gtavihubspain](https://www.tiktok.com/@gtavihubspain)

> 📖 **Documentación Completa:** Consulta la [**Guía de Uso Exhaustiva (`GUIA_DE_USO.md`)**](./GUIA_DE_USO.md) para ver tutoriales paso a paso, arquitectura, parámetros y directrices legales.

---

## ⚡ Capacidades Principales

1. **Estilo Visual Broadcast (Alex Hormozi / CapCut Pro):**
   - Reencuadre vertical centrado al **83.3%** (`1080x1600 px`) con cojines de *velvet blur* superior e inferior.
   - Píldora de cristal oscuro con titular de gancho de alto impacto (`0.0s a 2.5s`).
   - Subtítulos dinámicos palabra por palabra con **Pop Bounce (`+4px`)**, halo neón dorado/rosa y **emojis contextuales nativos de Apple** (🗺️, 🚨, 🤯, 😂, 💰, 🏎️).
   - Audio masterizado automáticamente a nivel móvil (`-14 LUFS` EBU R128).

2. **Publicación Multiplataforma Inteligente:**
   - **YouTube Shorts:** Subida mediante API v3 oficial con OAuth2 (`token.json`).
   - **TikTok Creator Center:** Navegación por navegador local con perfil persistente en tu Mac M4 (IP residencial, WebGL GPU y cookies humanas).
   - **Instagram Reels:** Meta Graph API oficial o sesión local guardada.
   - **Motor de Escalonamiento (*Staggering*):** Retardos aleatorios humanos de 10 a 16 minutos entre redes para evitar detección de bots.

3. **Blindaje Legal Anti-Ban y Respeto al Creador:**
   - Transformación editorial sustancial bajo la doctrina de **Fair Use** (Artículo 107 de la Copyright Act de 1976).
   - Atribución obligatoria al autor original con enlace URL directo.
   - Límite orgánico estricto de **2 a 3 vídeos diarios** por plataforma.
   - Auditoría normativa periódica cada 7 días (`./run.sh audit`).

4. **Monitorización y Operación Desatendida:**
   - Panel de control de salud y cuotas en tiempo real (`./run.sh status`).
   - Notificaciones nativas en el Centro de Notificaciones de macOS.
   - Servicio en segundo plano con `launchd` de macOS en horas punta (14:00 y 19:30).

---

## 🚀 Comandos Rápidos

```bash
# Ver el panel de control y cuotas del pipeline
./run.sh status

# Auditar las políticas normativas de YouTube, TikTok y Meta
./run.sh audit

# Simular publicación multiplataforma en modo Sandbox seguro
./run.sh --url "<ENLACE>" --publish-all --dry-run

# Procesar y abrir inmediatamente en QuickTime para inspección visual
./run.sh --url "<ENLACE>" --preview

# Iniciar sesión persistente en TikTok e Instagram
./run.sh login-social

# Escaneo autónomo de canales configurados en channels.json
./run.sh --auto
```

---

## 📂 Enlaces a la Documentación del Repositorio

- [**Guía Completa de Uso y Manual de Operación (`GUIA_DE_USO.md`)**](./GUIA_DE_USO.md)
- [**Directrices Operativas, Formato Visual y Seguridad Anti-Ban (`DIRECTRICES.md`)**](./DIRECTRICES.md)
- [**Lista de Canales Monitorizados (`channels.json`)**](./channels.json)
- [**Servicio Autónomo para macOS (`assets/com.gtavihub.automation.plist`)**](./assets/com.gtavihub.automation.plist)
