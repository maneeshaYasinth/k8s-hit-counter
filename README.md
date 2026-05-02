# k8s-hit-counter ☸️

A simple hit counter app deployed on a local Kubernetes cluster using [kind](https://kind.sigs.k8s.io/).

## Stack
- **App:** Python (Flask)
- **Cache/Store:** Redis
- **Orchestration:** Kubernetes (kind)

## Architecture
[Browser] → NodePort → [API Deployment (2 replicas)] → ClusterIP → [Redis Deployment]

## K8s Concepts Covered
- Namespaces
- Deployments & ReplicaSets
- ClusterIP & NodePort Services
- ConfigMaps
- Secrets
- Readiness Probes
- Self-healing (delete a pod, watch it come back)

## Running Locally

### Prerequisites
- Docker
- [kind](https://kind.sigs.k8s.io/)
- kubectl

### Steps
```bash
# 1. Create cluster
kind create cluster --name k8s-lab

# 2. Build & load image
docker build -t hit-counter:v1 ./app
kind load docker-image hit-counter:v1 --name k8s-lab

# 3. Deploy
kubectl apply -f k8s/

# 4. Port forward
kubectl port-forward svc/api-service 8080:80 -n hit-counter

# 5. Hit it
curl localhost:8080
```

## Troubleshooting

- Typo in readiness probe: if you see "strict decoding error: unknown field \"spec.template.spec.containers[0].redinessProbe\"",
	check `k8s/api-deployment.yaml` for `redinessProbe` and change it to `readinessProbe`. Also ensure `initialDelaySeconds` and
	`periodSeconds` are indented at the same level as `httpGet` under `readinessProbe`.
- Namespace not found after create: if `kubectl apply -f k8s/` reports the namespace was created but later resources fail with
	"namespaces \"hit-counter\" not found", apply the namespace first and wait before applying the rest:
	```bash
	kubectl apply -f k8s/namespace.yaml
	kubectl wait --for=condition=Established namespace/hit-counter --timeout=10s || sleep 2
	kubectl apply -f k8s/
	```
- Local image tips: if you use `imagePullPolicy: Never`, build and load the image into kind before applying manifests:
	```bash
	docker build -t hit-counter:v1 ./app
	kind load docker-image hit-counter:v1 --name k8s-lab
	```