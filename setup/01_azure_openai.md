# Setup Guide 1 — Azure OpenAI

Corvin uses Azure OpenAI (via LiteLLM) to generate RCA and fix strategy.
You need a resource with two model deployments: `gpt-4o` and `gpt-4o-mini`.

---

## Step 1 — Create the Azure OpenAI resource

In the Azure Portal:

1. Search for **Azure OpenAI** → click **Create**
2. Fill in:
   - **Subscription**: your subscription
   - **Resource group**: create new or pick existing (e.g. `rg-corvin`)
   - **Region**: `East US` or `Sweden Central` (best gpt-4o availability as of 2026)
   - **Name**: `corvin-ai` (or any name you like)
   - **Pricing tier**: Standard S0
3. Click **Review + Create** → **Create**

Or via Azure CLI:
```powershell
az cognitiveservices account create `
  --name corvin-ai `
  --resource-group rg-corvin `
  --kind OpenAI `
  --sku S0 `
  --location eastus
```

---

## Step 2 — Deploy gpt-4o

1. Open your Azure OpenAI resource → **Azure OpenAI Studio** → **Deployments**
2. Click **Deploy model** → **Deploy base model**
3. Select **gpt-4o** → click **Confirm**
4. Set:
   - **Deployment name**: `gpt-4o`  ← must match exactly
   - **Model version**: latest available
   - **Tokens per minute**: 10K minimum (higher = faster investigations)
5. Click **Deploy**

Or via CLI:
```powershell
az cognitiveservices account deployment create `
  --name corvin-ai `
  --resource-group rg-corvin `
  --deployment-name gpt-4o `
  --model-name gpt-4o `
  --model-version "2024-11-20" `
  --model-format OpenAI `
  --sku-name Standard `
  --sku-capacity 10
```

---

## Step 3 — Deploy gpt-4o-mini (fallback)

Repeat Step 2 with:
- **Deployment name**: `gpt-4o-mini`
- **Model**: gpt-4o-mini

---

## Step 4 — Get your API key and endpoint

In your Azure OpenAI resource → **Keys and Endpoint**:

- Copy **Key 1** — this is your `AZURE_OPENAI_API_KEY`
- Copy **Endpoint** — looks like `https://corvin-ai.openai.azure.com/`

---

## Step 5 — Set environment variables

Add to your `.env` file (see [04_env_file.md](04_env_file.md)):

```env
AZURE_OPENAI_API_KEY=<paste Key 1 here>
AZURE_OPENAI_API_BASE=https://corvin-ai.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01
```

LiteLLM reads these automatically when the model name is prefixed with `azure/`
(already set in `config/models/llm.yaml` as `azure/gpt-4o`).

---

## Verify

Start the API and run a health check:
```powershell
uvicorn apps.api.main:app --reload
# In another terminal:
curl http://localhost:8000/health
```

Then try an investigation from the CLI — if the LLM is wired correctly you'll
get a real RCA instead of an error.
