# Setup Guide 5 — AKS (Azure Kubernetes Service)

Corvin uses the AKS adapter to inspect pod health, container events, and
deployment status. This is a read-only connection — Corvin cannot modify
your cluster in V1 or V1.5.

The values you need at the end:
- `AKS_CLUSTER_NAME`
- `AKS_RESOURCE_GROUP`
- `AKS_NAMESPACE` (the namespace your Java app runs in)

---

## Step 1 — Confirm your AKS cluster name and resource group

```powershell
az aks list --output table
```

Note the **Name** and **ResourceGroup** columns for your cluster.

---

## Step 2 — Get credentials (set up kubeconfig)

This merges your AKS credentials into your local `~/.kube/config` file,
which is what the Python `kubernetes` library reads automatically:

```powershell
az aks get-credentials `
  --resource-group <your-resource-group> `
  --name <your-cluster-name> `
  --overwrite-existing
```

Verify it worked:
```powershell
kubectl get nodes
```

**Pass:** You see your AKS nodes listed.
**Fail:** `Unauthorized` or `connection refused` — check your Azure CLI login with `az login`.

---

## Step 3 — Find the namespace your Java app runs in

```powershell
kubectl get namespaces
kubectl get deployments --all-namespaces
```

Look for your Java Spring Boot service deployments and note which namespace
they are in (e.g. `default`, `production`, `apps`).

---

## Step 4 — Verify Corvin can read your pods

Run a quick test to confirm read access works:

```powershell
kubectl get pods -n <your-namespace>
kubectl describe pod <any-pod-name> -n <your-namespace>
```

Both commands must return data without any permission errors.

---

## Step 5 — Add to `.env`

```env
AKS_CLUSTER_NAME=<your-cluster-name>
AKS_RESOURCE_GROUP=<your-resource-group>
AKS_NAMESPACE=<namespace-where-your-app-runs>
```

---

## Step 6 — Update `knowledge/site.md`

Open `knowledge/site.md` and fill in the AKS section with the real values:

```markdown
## AKS Cluster

- Cluster name:        `<your-cluster-name>`
- Resource group:      `<your-resource-group>`
- Region:              `<your-region>`
- Node pool name:      `<your-node-pool>`
- Kubernetes version:  `<your-k8s-version>`
- Default namespace:   `<your-app-namespace>`
```

Get exact values:
```powershell
# Cluster details
az aks show --name <cluster> --resource-group <rg> --query "{version:kubernetesVersion, region:location, nodePool:agentPoolProfiles[0].name}" --output table

# Kubernetes version
kubectl version --short
```

---

## Smoke Test

After the `.env` is filled and `kubectl` is working, run this to verify the
Python adapter can connect:

```powershell
python - <<'EOF'
from corvin.adapters.aks_adapter import AKSAdapter
adapter = AKSAdapter()
pods = adapter.list_pods(namespace="default")
print(f"AKS pods visible: {len(pods)}")
print("PASS: AKS adapter connected successfully")
EOF
```

**Pass:** Prints `PASS`.
**Fail:** `ConfigException` — means kubeconfig is not found or not valid.
