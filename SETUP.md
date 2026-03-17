# Setup Instructions for Intelligence Module

##  Estructura del Módulo

```
module-intelligence/
├── app.py                          # FastAPI application
├── Dockerfile                      # Docker image para Data Science
├── requirements.txt                # Dependencias Python
├── README.md                       # Documentación principal
├── MIGRATION.md                    # Guía de migración
├── SETUP.md                        # Este archivo
├── .gitignore                      # Git ignore
├── .dockerignore                   # Docker ignore
├── intelligence_service/           # Código Python
│   ├── __init__.py
│   ├── core/                       # Módulos core
│   │   ├── redis_client.py
│   │   ├── orion_client.py
│   │   ├── job_queue.py
│   │   └── worker.py
│   └── plugins/                    # Plugins de análisis
│       ├── base.py
│       └── simple_predictor.py
└── k8s/                            # Manifests Kubernetes
    ├── deployment.yaml
    └── ingress.yaml
```

##  Estructura del Módulo

```
module-intelligence/
├── backend/                     # Backend FastAPI application
│   ├── app/
│   │   ├── main.py             # FastAPI app factory
│   │   ├── config.py           # Configuration (pydantic-settings)
│   │   ├── api/                # API routes
│   │   ├── core/               # Core modules (jobs, worker, orion)
│   │   ├── plugins/            # Analysis plugins
│   │   └── middleware/         # Auth middleware (optional)
│   ├── tests/                  # Test suite
│   ├── Dockerfile              # Multi-stage build for Data Science
│   └── requirements.txt        # Python dependencies
├── k8s/                        # Kubernetes manifests
│   ├── backend-deployment.yaml
│   └── registration.sql
├── .github/workflows/          # CI/CD
│   └── build-push.yml
├── manifest.json               # Module metadata for registration
├── env.example                 # Environment template
└── README.md                   # This file
```

##  Pasos para Crear el Repositorio GitHub

### Paso 1: Revisar el contenido

```bash
cd module-intelligence/
ls -la
tree -L 3  # Ver estructura completa
```

### Paso 2: Crear repositorio en GitHub

1. Ve a https://github.com/k8-benetis
2. Click en "New repository"
3. Nombre: `nekazari-module-intelligence`
4. Descripción: "Standalone AI/ML Intelligence Module for Nekazari Platform"
5. **NO** inicialices con README, .gitignore, o licencia (ya los tenemos)
6. Click "Create repository"

### Paso 3: Inicializar Git y hacer push

```bash
# Ya estás en module-intelligence/
git init
git add .
git commit -m "feat: Initial commit - Intelligence Module v1.0

- Standalone FastAPI service for AI/ML analysis
- Redis-based async job queue
- Orion-LD integration for Prediction entities
- Plugin architecture for extensibility
- Kubernetes manifests included"

# Conectar con el repositorio remoto (reemplaza <repo-url> con la URL de GitHub)
git remote add origin https://github.com/k8-benetis/nekazari-module-intelligence.git

# Push inicial
git branch -M main
git push -u origin main
```

### Paso 4: Verificar

Ve a https://github.com/k8-benetis/nekazari-module-intelligence y verifica que todos los archivos estén presentes.

##  Configuración Local (Testing)

### Instalar dependencias

```bash
cd module-intelligence/
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Variables de entorno

Crea un archivo `.env`:

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

ORION_URL=http://localhost:1026
CONTEXT_URL=https://YOUR_PLATFORM_DOMAIN/ngsi-ld-context.json

LOG_LEVEL=INFO
```

### Ejecutar localmente

```bash
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

### Probar endpoints

```bash
# Health check
curl http://localhost:8080/health

# List plugins
curl http://localhost:8080/api/intelligence/plugins
```

##  Build Docker Image

```bash
# Build local
docker build -t nekazari-module-intelligence:latest .

# Test local
docker run -p 8080:8080 \
  -e REDIS_HOST=host.docker.internal \
  -e ORION_URL=http://host.docker.internal:1026 \
  nekazari-module-intelligence:latest
```

##  CI/CD Setup (Opcional)

Crea `.github/workflows/build.yml` en el nuevo repositorio:

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Login to GitHub Container Registry
        uses: docker/login-action@v2
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ghcr.io/k8-benetis/nekazari-module-intelligence:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

##  Checklist Final

- [ ] Repositorio creado en GitHub
- [ ] Código pusheado
- [ ] README.md visible en GitHub
- [ ] Dockerfile presente
- [ ] Manifests K8s presentes
- [ ] CI/CD configurado (opcional)

##  Próximos Pasos

1. **Desplegar en Kubernetes**: Usa los manifests en `k8s/`
2. **Integrar con Core**: El Core debe llamar a la API REST del módulo
3. **Añadir ML**: Descomenta librerías en `requirements.txt` cuando las necesites

##  Notas

- Este módulo es **completamente independiente** del Core
- La única comunicación es vía REST API y Orion-LD
- No hay dependencias compartidas
- Está preparado para escalar independientemente

