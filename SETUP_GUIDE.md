# Local Setup Guide - YOLO Flagellar Motor Detection

This guide will help you deploy this project on a new PC.

## Prerequisites

1. **Python 3.8 or higher**
   - Download from: https://www.python.org/downloads/
   - During installation, check "Add Python to PATH"

2. **Git** (optional, for cloning)
   - Download from: https://git-scm.com/downloads/

## Quick Setup (Automated)

1. **Extract or clone the project** to your desired location

2. **Run the setup script** (PowerShell):
   ```powershell
   .\setup.ps1
   ```

3. **Start the application**:
   ```powershell
   .\restart.ps1
   ```

4. **Access the application**:
   - Frontend: http://localhost:8001
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Manual Setup

If the automated setup fails, follow these steps:

### Step 1: Install Python Dependencies

```powershell
# Navigate to the project directory
cd "path\to\yolo_project localhost"

# Install backend dependencies
cd backend
pip install -r requirements.txt
cd ..

# Install frontend dependencies (if any)
cd frontend
pip install -r requirements.txt
cd ..
```

### Step 2: Verify Model Files

Ensure you have one of these model files in the `backend/` directory:
- `best.pt` (PyTorch model)
- `best.quant.onnx` (Quantized ONNX model - faster)

### Step 3: Start the Services

```powershell
.\restart.ps1
```

This will start:
- Backend on port 8000
- Frontend on port 8001

## Project Structure

```
yolo_project localhost/
├── backend/
│   ├── main.py              # FastAPI backend server
│   ├── requirements.txt     # Python dependencies
│   ├── best.pt             # YOLO model (PyTorch)
│   ├── best.quant.onnx     # YOLO model (ONNX, optional)
│   └── outputs/            # Detection results stored here
├── frontend/
│   ├── index.html          # Main UI
│   ├── script.js           # Frontend logic
│   └── serve_frontend.py   # Frontend server
├── restart.ps1             # Start both services
├── setup.ps1               # Automated setup
└── SETUP_GUIDE.md          # This file

```

## Configuration

### Port Configuration

To change the default ports, edit the files:

**Backend Port (default: 8000):**
- Edit `backend/main.py`, line at bottom:
  ```python
  port = int(os.environ.get("PORT", 8000))  # Change 8000
  ```

**Frontend Port (default: 8001):**
- Edit `frontend/serve_frontend.py`:
  ```python
  PORT = 8001  # Change this value
  ```

### CORS Configuration

If you change ports, update CORS settings in `backend/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001"],  # Update port here
    ...
)
```

## Troubleshooting

### Port Already in Use

If you see "port already in use" error:

1. **Find and kill the process** (PowerShell):
   ```powershell
   # Find process using port 8000
   netstat -ano | findstr :8000
   
   # Kill the process (replace PID with actual process ID)
   taskkill /PID <PID> /F
   ```

2. **Or change the port** (see Configuration section above)

### Module Not Found Errors

```powershell
# Reinstall dependencies
cd backend
pip install --upgrade -r requirements.txt
```

### Model File Missing

Download or copy your trained model file:
- Place `best.pt` or `best.quant.onnx` in `backend/` directory

### Python Not Recognized

1. Ensure Python is installed
2. Add Python to PATH:
   - Windows Settings → System → Advanced → Environment Variables
   - Add Python installation directory to PATH

### Cannot Access Frontend

1. Check if both services are running:
   ```powershell
   # Should show processes on ports 8000 and 8001
   netstat -ano | findstr "8000 8001"
   ```

2. Try accessing alternative UI:
   - http://localhost:8000/frontend/

## Testing the Installation

1. **Check backend health**:
   ```powershell
   curl http://localhost:8000/
   ```
   Should return: `{"status":"ok"}`

2. **Upload a test file**:
   - Go to http://localhost:8001
   - Upload a ZIP file containing tomogram images
   - Wait for processing to complete

## Stopping the Services

Press `Ctrl+C` in the PowerShell window running the services, or:

```powershell
# Kill all Python processes (use with caution)
taskkill /F /IM python.exe
```

## System Requirements

- **OS**: Windows 10/11, Linux, macOS
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 2GB for project + space for uploads/results
- **CPU**: Multi-core processor recommended for faster inference

## Additional Resources

- FastAPI Documentation: https://fastapi.tiangolo.com/
- YOLO Documentation: https://docs.ultralytics.com/
- Python Virtual Environments: https://docs.python.org/3/tutorial/venv.html

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs in the PowerShell window
3. Check `backend/outputs/` for error logs
