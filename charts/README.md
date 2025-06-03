# vision-service Helm Chart

## Overview

This Helm chart deploys a vision-service.

It includes:

- **StatefulSet**: Deploys vision-service with the specified number of replicas.
- **Service**: A headless Service to expose vision-service.

## Installation

### 1. Lint the Chart

```bash
helm lint ./deployments/vision-service
```

### 2. Render Templates

```bash
helm template 2060-vision-service-blue ./deployments/vision-service --namespace demos
```

### 3. Dry-Run Installation

```bash
helm install --dry-run --debug 2060-vision-service-blue ./deployments/vision-service --namespace demos
```

### 4. Install the Chart

```bash
helm upgrade --install 2060-vision-service-blue ./deployments/vision-service --namespace demos --wait
```

## Uninstalling the Chart

```bash
helm uninstall  2060-vision-service-blue  --namespace demos
```

For more information, refer to the [Helm documentation](https://helm.sh/docs/).

## Notes

- Ensure that any pre-existing resources in the namespace do not conflict with those defined in this chart.
