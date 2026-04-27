# 07 — Teams Bot Registration (V2 ChatOps)

This guide registers Corvin as a real Microsoft Teams bot so SREs can
`@Corvin investigate order-service production` and receive a live RCA card.

---

## What you need before starting

| Prerequisite | Where to get it |
|---|---|
| Azure CLI logged in | `az login` |
| An Azure subscription | `az account show` |
| A publicly reachable HTTPS endpoint for Corvin API | ngrok, Azure App Service, or AKS Ingress |
| Corvin API running | `uvicorn apps.api.main:app --reload --port 8000` |

---

## Step 1 — Create an Azure Bot resource

```powershell
# Pick a unique name for your bot, e.g. "corvin-bot"
$BOT_NAME   = "corvin-bot"
$RG         = "corvin-rg"          # your existing resource group
$REGION     = "eastus"

# Create the Bot Channels Registration (free tier is fine)
az bot create `
  --resource-group $RG `
  --name $BOT_NAME `
  --kind registration `
  --location global `
  --sku F0
```

> **Note:** If `az bot create` is not available, use the Azure Portal:
> Portal → Create resource → search "Azure Bot" → fill the form with the same values.

---

## Step 2 — Get the App ID and create a client secret

After the bot is created:

```powershell
# Get the Microsoft App ID (will look like a UUID)
az bot show --resource-group $RG --name $BOT_NAME --query "properties.msaAppId" -o tsv
```

Copy the **App ID** value — this is your `TEAMS_APP_ID`.

Now create a client secret:

1. Go to **Azure Portal → Azure Active Directory (Entra ID) → App registrations**
2. Find the app named `corvin-bot` (or the App ID from above)
3. Click **Certificates & secrets → New client secret**
4. Set expiry to 24 months → click **Add**
5. Copy the **Value** immediately (it disappears after you leave the page)

This value is your `TEAMS_APP_PASSWORD`.

---

## Step 3 — Set the messaging endpoint

Corvin's Teams bot endpoint is:

```
https://<YOUR-PUBLIC-URL>/teams/messages
```

Set it on the bot:

```powershell
az bot update `
  --resource-group $RG `
  --name $BOT_NAME `
  --endpoint "https://<YOUR-PUBLIC-URL>/teams/messages"
```

Or via Portal: Bot resource → **Configuration → Messaging endpoint** → paste URL → Save.

### For local development with ngrok

```powershell
ngrok http 8000
# Ngrok will give you a URL like: https://abc123.ngrok-free.app
# Use: https://abc123.ngrok-free.app/teams/messages
```

---

## Step 4 — Enable the Teams channel

```powershell
az bot msteams create --resource-group $RG --name $BOT_NAME
```

Or via Portal: Bot resource → **Channels → Microsoft Teams → Save**.

---

## Step 5 — Update your `.env` file

Open `.env` and fill in the values collected above:

```env
TEAMS_APP_ID=<paste App ID here>
TEAMS_APP_PASSWORD=<paste client secret here>
```

---

## Step 6 — Enable the bot in Corvin config

Open `config/integrations/teams.yaml` and set:

```yaml
bot_enabled: true
app_id: "${TEAMS_APP_ID}"
app_password: "${TEAMS_APP_PASSWORD}"
```

Restart the API:

```powershell
uvicorn apps.api.main:app --reload --port 8000
```

---

## Step 7 — Add the bot to a Teams channel

1. In Teams, click **Apps → Manage your apps → Upload a custom app**
   *(or ask your Teams admin if custom app upload is restricted)*
2. Alternatively, search the bot by name in Teams:
   - Click **...** (More added apps) → search `corvin-bot`
   - Click **Add to a team** → pick your channel

---

## Step 8 — Smoke test

In the Teams channel where Corvin is a member:

```
@Corvin investigate order-service production
```

Expected flow:
1. Corvin immediately sends: *"On it! Investigating order-service in production…"*
2. After ~30–60 seconds: an Adaptive Card with the full RCA appears
3. Card has **Approve & Execute** and **Reject** buttons

If the card doesn't appear, check:
- API logs: `uvicorn` console output
- Teams channel → Activity feed for delivery errors
- `TEAMS_APP_ID` / `TEAMS_APP_PASSWORD` match the bot registration

---

## Summary of what you created

| Resource | Purpose |
|---|---|
| Azure Bot (registration) | Bot identity + Teams channel registration |
| App Registration client secret | Bot auth (App ID + Password) |
| Teams channel on the bot | Enables the bot to appear in Teams |
| `bot_enabled: true` in config | Activates the `POST /teams/messages` route in Corvin |
