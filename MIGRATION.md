# Migration Guide: Intelligence Service → Module

## Overview

This module was extracted from `services/intelligence-service/` in the main nekazari-public repository to maintain strict architectural separation.

## What Changed

### ✅ Removed Dependencies

- ❌ No dependency on `services/common/`
- ❌ No shared code with Core services
- ✅ All functionality is self-contained

### ✅ Updated Files

1. **Dockerfile**: 
   - Removed `COPY services/common`
   - Optimized for Data Science workloads
   - No dependencies on monorepo structure

2. **Code**:
   - All imports are relative or absolute within this package
   - `orion_client.py` has its own `inject_fiware_headers` (no import from common)

3. **Requirements**:
   - Added placeholders for Data Science libraries
   - Ready to uncomment when ML is needed

## Migration Steps (for GitHub)

### Step 1: Create Repository

```bash
# On GitHub, create: nekazari-module-intelligence
```

### Step 2: Initialize Git

```bash
cd module-intelligence/
git init
git add .
git commit -m "Initial commit: Intelligence Module v1.0"
git branch -M main
git remote add origin https://github.com/nkz-os/nekazari-module-intelligence.git
git push -u origin main
```

### Step 3: Update Main Repository

Remove the old service:

```bash
# In nekazari-public repo
rm -rf services/intelligence-service/
```

### Step 4: Update CI/CD

Build and push images from the new repository:

```yaml
# .github/workflows/build.yml (in new repo)
name: Build and Push
on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build Docker image
        run: |
          docker build -t ghcr.io/nkz-os/nekazari-module-intelligence:latest .
          docker push ghcr.io/nkz-os/nekazari-module-intelligence:latest
```

### Step 5: Deploy

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/ingress.yaml
```

## Communication Contract

The module communicates with Core **only** through:

1. **Core → Module**: REST API calls
2. **Module → Core**: Writing Prediction entities to Orion-LD

No shared code, no direct imports. Pure API contract.


