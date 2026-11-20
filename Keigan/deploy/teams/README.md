# Keigan Teams app package

1. Replace `<TEAMS_BOT_APP_ID>` (the bot's Entra application client id) and `<KEIGAN_PUBLIC_HOST>` in `manifest.json`.
2. Add `keigan-color.png` (192x192) and `keigan-outline.png` (32x32) next to `manifest.json` and zip the three files (no folder inside the zip).
3. Upload the zip to the Teams admin center (Manage apps > Upload new app) or the organisation app catalog. Note the **Teams app catalog id**
   shown for the app (a GUID); set it as `TEAMS_APP_CATALOG_ID` in Keigan.
4. The manifest requests the resource-specific consent permission `ChatMessage.Read.Chat`, which lets Keigan read messages of the chats the app is installed in (and only those).

Full admin steps (Entra registration, Azure Bot, Graph permissions, environment variables) are listed in the S4 section of `My Plans/09_LEARNINGS_LOG.md`.
