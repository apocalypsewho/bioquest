# BIOQUEST

**Discover what hasn't been mapped yet.** · *Descubre lo que todavía no está en el mapa.*

Plataforma de exploración de biodiversidad: ocurrencias (iNaturalist + GBIF) con control de calidad,
modelos de distribución (MaxEnt, Random Forest, GLM o GAM + ensemble, con fondo corregido por sesgo), mapa de vacíos de muestreo,
un índice de prioridad explicable y misiones de campo.

---

## 1. Arquitectura

```
Next.js 14 + TypeScript + Tailwind + MapLibre   (frontend/, mobile-first, modo oscuro)
        │  REST (JSON)
FastAPI (backend/app)
 ├─ services/inaturalist.py   INaturalistService    → api.inaturalist.org/v1 (+ OAuth en www.inaturalist.org)
 ├─ services/gbif.py          GBIFService           → api.gbif.org/v1
 ├─ services/demo.py          DemoDataProvider      → datos ficticios (DEMO)
 ├─ services/hub.py           fusión de fuentes, procedencia explícita, errores visibles
 ├─ services/occurrence_qc.py pipeline QC → VALID / QUESTIONABLE / EXCLUDED + razón
 ├─ services/environment.py   EnvironmentalDataProvider (Demo, WorldClim; CHELSA/Copernicus/NASA preparados)
 ├─ services/sdm.py           DistributionModelService (MaxEnt-elapid, RF, GLM/GAM-pygam, ensemble, CV espacial,
 │                            fondo aleatorio o target-group)
 ├─ services/landcover.py     ESA WorldCover 10 m (teselas GeoTIFF locales) → hábitat en LIVE
 ├─ services/access.py        distancia a caminos/senderos (OpenStreetMap vía Overpass API)
 ├─ services/literature.py    LiteratureProvider (índice de literatura GBIF + Crossref)
 ├─ services/anomaly.py       detección de observaciones inusuales (sugerencia, nunca certificación)
 ├─ services/sampling_guide.py recomendaciones de muestreo por grupo taxonómico y hábitat
 ├─ services/sampling.py      Sampling Gap Score
 ├─ services/priority.py      ExplorationPriorityScore (transparente)
 ├─ services/explore.py       EXPLORE y zona de exploración por especie
 ├─ services/privacy.py       coordenadas públicas / aproximadas / privadas; taxones sensibles
 ├─ services/taxonomy_ai.py   TaxonSuggestionProvider (interfaz; sin modelo de visión real)
 ├─ services/storage.py       almacenamiento local o S3-compatible
 └─ routers/                  auth, taxa, occurrences, explore, models, missions, expeditions,
                              observations (+ sync offline, screening, refresco iNat), projects, discoveries,
                              profile, iNat OAuth, compare (+ literatura), admin
SQLAlchemy → SQLite (por defecto) o PostgreSQL/PostGIS (docker-compose)
```

Los cálculos pesados (QC, modelos, gaps, scores) se hacen en el backend; el frontend solo colorea
las grillas que recibe. Los modelos se ejecutan en segundo plano dentro del proceso (`asyncio` + hilo);
la fila `ModelRun` guarda el estado, así que se puede cambiar a Celery/RQ sin cambiar la API.

## 2. Cómo ejecutarlo

### Publicar en Internet desde el celular (Render, HTTPS)
1. Sube este repositorio a GitHub.
2. En el navegador del celular abre https://dashboard.render.com/blueprint/new, entra con GitHub,
   elige el repositorio y pulsa *Apply*. `render.yaml` crea el servicio web (Docker, plan gratuito) y una
   base PostgreSQL gratuita; la clave secreta se genera sola.
3. Cuando el despliegue termine, abre la URL `https://<nombre>.onrender.com` y en Chrome: ⋮ → *Instalar app*
   (o *Añadir a la pantalla de inicio*).

Límites del plan gratuito de Render: el servicio se duerme tras ~15 min sin uso (el primer acceso tarda
~1 min en despertar), tiene 512 MB de RAM (los modelos pesados pueden quedarse sin memoria), las fotos
subidas se pierden en cada reinicio (disco efímero) y la base PostgreSQL gratuita caduca a los 30 días
salvo que la pases a un plan de pago.

### Instalación rápida (Docker, con acceso desde el celular)
```bash
./install.sh            # usa la IP de tu computadora en la red WiFi
```
Luego abre `http://localhost:3000` en la computadora, o la dirección que muestra el script en el celular
(mismo WiFi). Se requiere Docker en la computadora; el celular solo necesita un navegador.
Sin HTTPS, el celular abre la app como página normal y el modo sin conexión no se activa; para eso hace falta un dominio con HTTPS.
Para instalarla como icono en el celular: Android (Chrome) → ⋮ → *Añadir a la pantalla de inicio*; iPhone (Safari) → Compartir → *Añadir a pantalla de inicio*.

### Opción A — local sin Docker (SQLite)
Requisitos: Python 3.11+, Node 20+.
```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000     # API en :8000 (docs en /docs)
# en otra terminal
cd frontend && npm install && npm run dev                                 # web en :3000
```
o simplemente `./dev.sh`. Abre http://localhost:3000, crea una cuenta (la primera es admin).
El modo **DEMO** está activo por defecto; cámbialo en *Settings*.

### Opción B — Docker (PostgreSQL + PostGIS)
```bash
docker compose up --build
# opcional, índices espaciales:
docker compose exec db psql -U bioquest -f - < backend/scripts/postgis_upgrade.sql
```

### Datos ambientales reales (necesarios para modelar en LIVE)
```bash
cd backend && ../.venv/bin/python scripts/download_worldclim.py --res 10m
```
Descarga WorldClim v2.1 (bio1, bio4, bio12, bio15, elevación) desde geodata.ucdavis.edu.
Sin estos archivos, el modelado LIVE se niega a correr (nunca usa el ambiente sintético con datos reales).

### Cobertura del suelo real (opcional, para el hábitat en LIVE)
```bash
cd backend && ../.venv/bin/python scripts/download_worldcover.py --bbox -76 -13 -74 -11   # minlon minlat maxlon maxlat
```
Descarga teselas ESA WorldCover 10 m 2021 v200 (3°×3°, 50–150 MB c/u) del bucket público de AWS.
Sin teselas, el hábitat en LIVE se muestra como “unknown”.

### Tests
```bash
cd backend && ../.venv/bin/python -m pytest -q          # 25 tests
cd frontend && npm run build                             # compila + typecheck
node frontend/e2e-demo-flow.cjs                         # recorrido del flujo DEMO en navegador (Playwright; API y web levantadas)
```

## 3. API keys / credenciales

| Servicio | ¿Necesario? | Variable |
|---|---|---|
| iNaturalist (lectura) | **No** | — (API pública; se respeta ~1 req/s) |
| GBIF (lectura) | **No** | — (API pública) |
| iNaturalist OAuth (“Connect iNaturalist” y enviar observaciones) | Solo para escribir | `BIOQUEST_INAT_CLIENT_ID`, `BIOQUEST_INAT_CLIENT_SECRET`, `BIOQUEST_INAT_REDIRECT_URI` — crea una app en https://www.inaturalist.org/oauth/applications/new con redirect `http://localhost:8000/api/inat/oauth/callback` |
| GBIF download API (DOI, >100k registros) | Opcional, no implementado | cuenta GBIF |
| OpenStreetMap Overpass (caminos) | **No** | `BIOQUEST_OVERPASS_URL` (por defecto overpass-api.de; respeta su política de uso) |
| Crossref / literatura GBIF | **No** | — (pon `BIOQUEST_CONTACT_EMAIL` para el “polite pool” de Crossref) |
| ESA WorldCover | **No** (descarga pública) | `BIOQUEST_LANDCOVER_DIR` si guardas las teselas en otro lugar |
| Mapa base | No | Por defecto CARTO Dark Matter (datos OSM). Para uso comercial o tráfico alto usa un proveedor con key: `NEXT_PUBLIC_MAP_STYLE_URL` (p. ej. MapTiler/Stadia) |
| S3 | Opcional | `BIOQUEST_STORAGE_BACKEND=s3`, `BIOQUEST_S3_BUCKET`, `BIOQUEST_S3_ENDPOINT_URL` + credenciales AWS estándar |
| Secreto de sesión | Sí en producción | `BIOQUEST_SECRET_KEY` |

Pon también `BIOQUEST_CONTACT_EMAIL` (va en el User-Agent, como piden iNaturalist y GBIF).
Ver `backend/.env.example` y `frontend/.env.example`.

## 4. Qué es real, qué es DEMO

Cada elemento de la UI lleva etiqueta: **LIVE DATA**, **DEMO DATA**, **MODEL OUTPUT · DEMO input / LIVE input**, **USER RECORD**.

**Funciona con datos reales (LIVE)**
- Búsqueda de taxones en iNaturalist y GBIF; perfil (taxonomía, fotos con atribución, conteos, países y años por facetas GBIF, última observación iNat).
- Ocurrencias georreferenciadas de iNaturalist (paginación `id_above`) y GBIF (300/página, cuenta los registros sin coordenadas).
- Pipeline QC completo y deduplicación iNat↔GBIF (dataset de iNat en GBIF, `catalogNumber`).
- Sampling gap y EXPLORE alrededor de tu posición GPS usando una muestra de observaciones de iNaturalist.
- Modelos MaxEnt/RF/GLM o GAM + ensemble con WorldClim v2.1 real (tras descargarlo), con fondo target-group
  (registros GBIF de la familia del taxón en el área; si no hay suficientes, cae a orden/clase o a fondo aleatorio y lo dice).
- Chequeo de país offline en el QC (reverse_geocoder, GeoNames): asigna país a registros sin país y marca discrepancias.
- Hábitat por ESA WorldCover (tras descargar las teselas) y distancia real a caminos/senderos de OpenStreetMap.
- Literatura en COMPARE SPECIES (índice de literatura de GBIF + Crossref), con enlaces DOI.
- Screening de observaciones inusuales: distancia al registro válido más cercano, altitud fuera de rango,
  idoneidad bajo el umbral p10 del último modelo → sugiere POTENTIAL RANGE EXTENSION / UNUSUAL OBSERVATION.
- Refresco de validación de iNaturalist: si tu observación llega a Research Grade, ganas el XP de validación (una vez).
- Proyectos colaborativos: crear, añadir miembros por usuario, compartir observaciones (con la privacidad del dueño).
- OAuth de iNaturalist y envío de observaciones/fotos (con consentimiento explícito por observación).
- Cuentas, misiones, expediciones con track GPS, observaciones con fotos/audio, cola offline + sincronización, descubrimientos, XP, perfil, privacidad de coordenadas.

**DEMO (ficticio, siempre etiquetado)**
- Taxones del género inventado *Demoquestia* (no existe), sus puntos, observaciones de esfuerzo y el ambiente sintético.
- Sugerencia de IA en modo DEMO. Hábitat en DEMO (derivado de la elevación sintética).
- La posición en DEMO es una “base de campo ficticia”, no tu ubicación.
- En DEMO, el “camino” es una línea ficticia (lat −12.0) y el fondo target-group usa registros de esfuerzo ficticios.
- COMPARE en DEMO no busca literatura (los taxones no existen).
- Las observaciones DEMO nunca pueden enviarse a iNaturalist.

**MODEL OUTPUT**: mapas de idoneidad, acuerdo entre modelos, extrapolación, Sampling Gap Score y Priority Score. Todos explicables (se muestran componentes y pesos).

## 5. Estado por fases

| Fase | Estado |
|---|---|
| 1 MVP ejecutable | ✅ Implementado. Flujo probado en navegador en DEMO. Las llamadas LIVE están probadas contra respuestas simuladas con la forma documentada de las APIs (ver Limitaciones). |
| 2 Modelado | ✅ QC (con chequeo de país offline), duplicados, coordenadas sospechosas, adelgazamiento espacial, colinealidad, MaxEnt (elapid), RF, GLM o GAM (pygam), fondo aleatorio o target-group, ensemble, CV espacial por bloques, AUC/TSS/matriz de confusión, extrapolación, raster en mapa. |
| 3 Inteligencia de exploración | ✅ Priority Score, selección automática de zonas (radio 5–50 km), accesibilidad (proxy para el ranking + distancia real a caminos OSM en la zona elegida), hábitat WorldCover, rareza, incertidumbre taxonómica, recomendaciones de muestreo por grupo y hábitat (etiquetadas como guía general). |
| 4 Campo | ✅ GPS, track, fotos, audio, notas, hábitat, microhábitat, medidas, expediciones, cola offline (IndexedDB), sincronización idempotente y service worker (la app abre sin red tras una primera visita). Proyectos colaborativos. Las teselas del mapa no se guardan offline. |
| 5 IA taxonómica | 🟡 Interfaz `TaxonSuggestionProvider`, lenguaje correcto (“AI suggestion”), comparación morfológica, literatura (GBIF + Crossref), screening de registros inusuales, niveles de evidencia. **Sin modelo de visión real** (falta elegir proveedor/credenciales). |

## 6. Limitaciones científicas y técnicas (sin ocultar nada)

- **No pude probar las APIs reales desde el entorno de desarrollo**: la red de la máquina donde se construyó bloqueaba api.inaturalist.org, api.gbif.org, api.crossref.org, overpass-api.de, geodata.ucdavis.edu, el bucket de ESA WorldCover y las teselas del mapa. Los adaptadores siguen la documentación oficial y están probados con respuestas simuladas; la primera ejecución real en tu máquina es la verdadera prueba (usa *Settings → Test live sources*).
- La salida de los modelos es **idoneidad ambiental relativa** (presencia-fondo), no probabilidad de ocurrencia. AUC/TSS se calculan contra puntos de fondo, no ausencias reales.
- Corrección de sesgo con fondo **target-group** (por defecto en la UI): asume que el grupo de referencia (familia en GBIF) se muestreó con el mismo sesgo que la especie. Si hay <20 celdas con registros del grupo, se usa fondo aleatorio y se avisa. El adelgazamiento espacial (1 registro/celda) se mantiene.
- GAM (pygam): un spline penalizado por variable; si el ajuste no converge, se aumenta el suavizado (λ) automáticamente.
- Chequeo de país: usa el lugar GeoNames (≥1000 hab.) más cercano, no polígonos de fronteras; cerca de una frontera puede equivocarse, por eso solo marca QUESTIONABLE. Las pruebas de centroides de país, capitales, instituciones y mar/tierra **siguen sin ejecutarse** (se informa en el resumen QC).
- Con <10 celdas ocupadas tras el QC: *“Insufficient occurrence data for reliable model.”* y no se genera mapa.
- Resolución por defecto 10′ (~18 km) con WorldClim 10m; para microendemismos conviene 30″ (más memoria y tiempo).
- El esfuerzo de muestreo en LIVE se estima con una muestra (hasta 1000 observaciones recientes de iNaturalist en el área): sirve para patrones relativos, no absolutos.
- Accesibilidad: el ranking de celdas usa el proxy (distancia en línea recta + pendiente); la distancia real a caminos/senderos (OSM) se calcula solo para la zona elegida, para no saturar Overpass. OSM puede no tener mapeados caminos rurales. No considera áreas protegidas ni propiedad privada.
- Screening de observaciones: compara con registros públicos (que pueden tener coordenadas ocultas) y con el último modelo; una identificación incorrecta produce falsas alarmas. Es una sugerencia, nunca certificación.
- Literatura: los resultados de Crossref son coincidencias de texto y pueden no tratar del taxón; BIOQUEST no los resume ni interpreta.
- Hábitat en LIVE: requiere descargar las teselas ESA WorldCover del área; sin ellas se muestra “unknown”.
- Probado con SQLite; el esquema es compatible con PostgreSQL, pero **no lo ejecuté contra PostGIS** en este entorno.
- Autenticación simple (PBKDF2 + token firmado); para producción usar un proveedor OIDC.

## 7. Cómo reemplazar las abstracciones
- **Nueva fuente ambiental**: subclase de `EnvironmentalDataProvider` con `variables()` y `grid()`; regístrala en `PROVIDERS`.
- **Modelo de visión**: implementa `TaxonSuggestionProvider.suggest()` y devuélvelo en `get_vision()`.
- **Jobs**: reemplaza `asyncio.create_task(_execute(...))` en `routers/modeling.py` por una tarea Celery/RQ.
- **Literatura**: añade otra fuente (BHL, Plazi TreatmentBank) como método en `LiteratureProvider.search()`.

Fuentes: iNaturalist (https://www.inaturalist.org/pages/terms), GBIF.org (cita cada dataset), WorldClim v2.1 (Fick & Hijmans 2017), elapid (Anderson 2023), mapa © OpenStreetMap contributors © CARTO.
