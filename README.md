# YOLO FastAPI Full Project

Quick local run (development)

1. Put your `best.pt` model into the `backend/` folder.

2. **(Optional) Generate quantized model** for faster inference:

   ```powershell
   cd backend
   python quantize_model.py
   ```

   This creates `best.onnx` and `best.quant.onnx`. The backend automatically prefers `best.quant.onnx` if available, falling back to `best.pt`.

3. Create and activate a Python venv (recommended):

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

6. Open `frontend/index.html` in a browser and change `backendUrl` in `frontend/script.js` if needed.

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
