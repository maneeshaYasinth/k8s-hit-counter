# What I Learned Building a Hit Counter on Kubernetes

> Personal notes from working through a k8s project end-to-end — namespaces, deployments, services, secrets, configmaps, and how they all wire together.

---

## The Mental Model

Before anything clicked, I needed a way to think about k8s without drowning in YAML. This helped:

| k8s Concept | Real-World Analogy |
|---|---|
| Namespace | A district in a city |
| Pod | A building |
| Container | A room inside the building |
| Deployment | A property developer — builds and maintains buildings |
| Service | A post office — gives a stable address to find buildings |
| ConfigMap | A public notice board |
| Secret | A locked safe |

Everything in this project lives inside the `hit-counter` namespace. The pods talk to each other through Services.

---

## The Most Important Thing: Labels and Selectors

Files don't import each other. They don't reference file paths. The way k8s objects find each other is **pure string matching via labels and selectors**.

This is the mental shift that made everything else make sense.

```yaml
# redis-deployment.yaml
spec:
  selector:
    matchLabels:
      app: redis        # Deployment LOOKS FOR pods with this label
  template:
    metadata:
      labels:
        app: redis      # Pods GET this label when created
```

The Deployment manages what it creates — because it creates pods with a label it also searches for.

If `matchLabels` and `template.labels` ever diverge, the Deployment creates pods it can never find. Things break silently. That's a fun one to debug.

---

## How the Files Connect

```
namespace.yaml  (creates the "hit-counter" district)
       │
       ├── secret.yaml          (redis-secret)
       ├── configmap.yaml       (api-config)
       └── redis-deployment.yaml
               │  label: app=redis
               ▼
           redis-service.yaml
               selector: app=redis   ← routes traffic to redis pods
               │
       api-deployment.yaml
           reads secret by name
           reads configmap by name
           label: app=hit-counter-api
               │
               ▼
           api-service.yaml
               selector: app=hit-counter-api
```

### Connection 1 — Namespace

Every manifest declares:

```yaml
metadata:
  namespace: hit-counter
```

If resources are in different namespaces, they can't find each other. `namespace.yaml` creates the district first — everything else declares it lives there.

### Connection 2 — Service → Pod

```yaml
# redis-service.yaml
spec:
  selector:
    app: redis     # finds pods with this label — continuously
```

The Service watches the cluster. Scale to 3 Redis pods — all 3 get traffic. A pod dies, a new one starts with `app: redis` — the Service automatically picks it up. No manual update.

### Connection 3 — Pod → Secret

```yaml
# api-deployment.yaml
env:
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: redis-secret   # must match metadata.name in secret.yaml
        key: password        # must match the key inside the secret
```

k8s looks up the Secret named `redis-secret`, grabs the `password` key, and injects it as `REDIS_PASSWORD` into the container. The app reads it with `os.environ.get("REDIS_PASSWORD")`.

### Connection 4 — Pod → ConfigMap

```yaml
# api-deployment.yaml
envFrom:
  - configMapRef:
      name: api-config    # must match metadata.name in configmap.yaml
```

`envFrom` bulk-imports all keys from the ConfigMap as environment variables. So `REDIS_HOST=redis-service` lands in the container automatically.

### Connection 5 — Service Discovery via DNS

This was the most invisible connection. When the Flask app does:

```python
host = os.getenv('REDIS_HOST', 'localhost')
```

At runtime, `REDIS_HOST = "redis-service"`. k8s runs a built-in DNS server that auto-creates a DNS record for every Service:

```
redis-service → ClusterIP of redis-service → redis pod on port 6379
```

Services find each other by **name**, not IP. This is service discovery — and it just works.

---

## Key Concepts I Had to Actually Understand

### `apiVersion`

```yaml
apiVersion: v1        # core: Pod, Service, ConfigMap, Secret, Namespace
apiVersion: apps/v1   # workloads: Deployment, StatefulSet, DaemonSet
```

Different resource types live in different API groups. Think of it as which department in the k8s government handles the request.

### `envFrom` vs `env`

```yaml
envFrom:              # bulk import ALL keys from a ConfigMap or Secret
  - configMapRef:
      name: api-config

env:                  # import specific individual values
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: redis-secret
        key: password
```

### `ClusterIP` vs `NodePort`

| Type | Reachable From | Used For |
|---|---|---|
| `ClusterIP` | Inside the cluster only | Internal service-to-service (Redis) |
| `NodePort` | Outside the cluster | Exposing the API to the outside world |

### `readinessProbe`

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 5000
  initialDelaySeconds: 5
  periodSeconds: 5
```

Before k8s routes any traffic to a pod, it checks this endpoint. If the probe fails — the pod is marked "not ready" and the Service stops sending it traffic. Prevents users hitting a pod that's still booting or broken.

### `imagePullPolicy: Never`

```yaml
imagePullPolicy: Never
```

Normally k8s tries to pull images from a registry. `Never` tells it to only use images already loaded on the node — required when using `kind load docker-image` instead of pushing to a registry.

---

## Full Traffic Flow

```
curl localhost:8080
      │
      ▼
port-forward tunnel (local terminal → cluster)
      │
      ▼
api-service (NodePort, port 80)
  selector: app=hit-counter-api
      │
      ▼
hit-counter-api pod (Flask on port 5000)
  REDIS_HOST=redis-service  (from ConfigMap)
  REDIS_PASSWORD=***        (from Secret)
  calls r.incr('hits')
      │
      ▼
redis-service (ClusterIP)
  DNS: "redis-service" → ClusterIP → redis pod
      │
      ▼
redis pod (port 6379)
  increments "hits", returns count
      │
      ▼ (response travels back)
"Hit counter: 5."
```

---

## Commands I Used Most

```bash
# See everything in the namespace
kubectl get all -n hit-counter

# Watch pod state changes in real time
kubectl get pods -n hit-counter -w

# Dig into why something's wrong (check Events at the bottom)
kubectl describe pod <pod-name> -n hit-counter

# See app logs
kubectl logs -f <pod-name> -n hit-counter

# Logs from all pods matching a label
kubectl logs -l app=hit-counter-api -n hit-counter

# Shell into a running container (k8s equivalent of SSH)
kubectl exec -it <pod-name> -n hit-counter -- sh

# Check what env vars the container actually sees
kubectl exec -it <pod-name> -n hit-counter -- env | grep REDIS

# Test DNS from inside a pod
kubectl exec -it <pod-name> -n hit-counter -- nslookup redis-service

# Rolling restart (no downtime)
kubectl rollout restart deployment/hit-counter-api -n hit-counter

# Scale up/down
kubectl scale deployment hit-counter-api --replicas=3 -n hit-counter

# Apply all manifests in a directory
kubectl apply -f k8s/

# Tear it all down
kubectl delete -f k8s/
```

---

## TL;DR Takeaways

- **Labels and selectors are the glue.** Nothing in k8s connects via file imports or direct references — it's all string matching on labels.
- **Namespace everything.** Resources in different namespaces can't talk to each other by default.
- **Services give stable addresses.** Pods are ephemeral — IPs change. Services stay. DNS resolves service names automatically.
- **Secrets and ConfigMaps inject config at runtime.** The app code doesn't need to know where the values come from.
- **`kubectl describe` + `kubectl logs` is 90% of debugging.** Start there before anything else.