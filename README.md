# YOLO Flagellar Motor Detection System

A FastAPI-based application for detecting flagellar motors in cryo-electron tomography images using YOLO object detection.

## 🚀 Quick Start (New PC Setup)

**First time setup:**
```powershell
.\setup.ps1
```

**Start the application:**
```powershell
.\restart.ps1
```

**Access:**
- Frontend: http://localhost:8001
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

📖 **Detailed Instructions**: See [SETUP_GUIDE.md](SETUP_GUIDE.md) for complete setup instructions.

📦 **Deployment Guide**: See [DEPLOYMENT.md](DEPLOYMENT.md) for moving to a new PC.

## Features

- **Automated Detection**: YOLO-based flagellar motor detection in tomograms
- **3D Clustering**: DBSCAN clustering for 3D motor localization
- **Image Preprocessing**: Automated Otsu thresholding and masking
- **Volume Generation**: Creates 3D volumes for visualization
- **Real-time Progress**: Streaming updates during processing
- **History Tracking**: Saves detection results for analysis

## Requirements

- Python 3.8 or higher
- 8GB RAM minimum (16GB recommended)
- Model file: `best.pt` or `best.quant.onnx` in `backend/` directory

---

## Manual Setup (Advanced)

### 1. Put your model file

Put your `best.pt` model into the `backend/` folder.

### 2. (Optional) Generate quantized model

For faster inference:

```powershell
cd backend
python quantize_model.py
```

This creates `best.onnx` and `best.quant.onnx`. The backend automatically prefers `best.quant.onnx` if available, falling back to `best.pt`.

### 3. Create and activate a Python venv (recommended):

- Windows PowerShell:

  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```

- macOS / Linux:
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  ```

4. Install dependencies:

   ```powershell
   pip install -r backend/requirements.txt
   ```

5. Run the backend (dev):

   ```powershell
   cd backend
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

6. Run the frontend locally (recommended for CORS and API calls):

    - To serve the classic frontend:
       ```powershell
       cd frontend
       python serve_frontend.py
       ```
       Then open [http://localhost:8080](http://localhost:8080) in your browser.

    - To serve the new frontend:
       ```powershell
       cd newfront
       python serve_newfront.py
       ```
       Then open [http://localhost:8081](http://localhost:8081) in your browser.

    Both scripts add CORS headers for local API calls to the backend.

    If you prefer, you can still open the HTML files directly, but some browsers may block API requests due to CORS.

7. The frontend will auto-detect the backend URL if run from localhost. If you need to override, edit `frontend/config.js` or `newfront/script.js`.

Docker (backend)

1. Build image (from repo root):

   ```powershell
   docker build -t yolo-backend .
   ```

2. Run (examples):

   - Using Git Bash / WSL (Linux-like `pwd`):

     ```bash
     docker run -p 8000:8000 -v $(pwd)/backend/best.pt:/app/best.pt yolo-backend
     ```

   - Using Windows PowerShell (attempt to convert path to forward-slashes):

     ```powershell
     $p = (Get-Location).Path -replace '\\','/' ; docker run -p 8000:8000 -v "$p/backend/best.pt:/app/best.pt" yolo-backend
     ```

   - If you have issues mapping the file on Windows, copy `best.pt` into the container after starting it, or use Docker Desktop shared drives / WSL.

Helper scripts

- `backend/run_backend.ps1` — creates a venv (if missing), installs requirements (optionally), and runs the backend using the venv's Python. Run from `backend\` as `..\backend\run_backend.ps1 -Install` to create venv and install packages, then again without `-Install` to just run.
- `docker-run.ps1` — builds the Docker image and runs it while attempting to generate a Docker-friendly mount path on Windows.

Notes

- The backend automatically loads models in this order: `best.quant.onnx` (quantized) → `best.pt` (PyTorch). Use `quantize_model.py` to generate the quantized version.
- Quantization uses selective int8 for MatMul/Gemm operations only, skipping Conv layers for better YOLO performance.
- The frontend posts a `.zip` containing images to `/detect/` and will receive annotated image URLs under `/outputs/`.

If you want, I can run linting, add a `requirements.txt` pin file, or create a `docker-compose.yml` next.
