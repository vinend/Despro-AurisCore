# AurisCore

AurisCore is split into two independent programs:

| Folder | Purpose |
|---|---|
| [`WebApp/`](WebApp/) | Next.js interface, WebSocket client, and ESP32-compatible mock device |
| [`AI-Pipeline/`](AI-Pipeline/) | PCG dataset preparation, model training, evaluation, and inference |

## Web application

```powershell
cd WebApp
npm install
npm run dev
```

Run the simulated device in a second terminal:

```powershell
cd WebApp/mini-services/mock-device
npm install
npm run dev
```

See [`WebApp/README.md`](WebApp/README.md) for architecture and verification details.

## AI pipeline

```powershell
cd AI-Pipeline
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

Training is orchestrated by `python scripts/run_pipeline.py`. Inference against a saved model is available through `python scripts/predict.py path/to/recording.wav`. See [`AI-Pipeline/README.md`](AI-Pipeline/README.md) for dataset, training, evaluation, and inference documentation.

The web prototype currently uses a simulated classifier. Connecting it to the trained Python model is a separate integration step; the folder split does not imply clinical readiness.
