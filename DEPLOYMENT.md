# Deployment Guide - Moving to a New PC

This guide explains how to deploy this project on a completely new PC.

## Package Files to Transfer

### Option 1: Full Project Transfer (Recommended)

Transfer the entire project folder containing:
```
yolo_project localhost/
├── backend/              (Required)
├── frontend/             (Required)
├── setup.ps1            (Required)
├── restart.ps1          (Required)
├── SETUP_GUIDE.md       (Helpful)
├── DEPLOYMENT.md        (This file)
└── README.md            (Helpful)
```

### Option 2: Minimal Transfer

At minimum, you need:
- `backend/` folder (with main.py and model files)
- `frontend/` folder (with all HTML/JS/CSS files)
- `setup.ps1` (setup script)
- `restart.ps1` (start script)

## Step-by-Step Deployment on New PC

### 1. Install Prerequisites

**Python 3.8+**
- Download: https://www.python.org/downloads/
- ⚠️ **IMPORTANT**: Check "Add Python to PATH" during installation

**Verify Installation:**
```powershell
python --version
pip --version
```

### 2. Transfer Project Files

Choose one method:

**Method A: USB Drive/Network Transfer**
- Copy the entire `yolo_project localhost` folder
- Place it anywhere on the new PC (e.g., `C:\Projects\`)

**Method B: Git Clone** (if using version control)
```powershell
git clone <repository-url>
cd yolo_project localhost
```

**Method C: ZIP Archive**
- Compress the project folder
- Transfer and extract on new PC

### 3. Run Setup Script

```powershell
# Open PowerShell in the project directory
cd "C:\path\to\yolo_project localhost"

# If execution policy error, run:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Run setup
.\setup.ps1
```

The setup script will:
- ✓ Check Python installation
- ✓ Install all dependencies
- ✓ Verify model files
- ✓ Create necessary directories

### 4. Start the Application

```powershell
.\restart.ps1
```

### 5. Access the Application

- **Frontend**: http://localhost:8001
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Model Files - Important!

Your model files are **NOT** included in typical version control. You must:

1. **Locate your model files** on the original PC:
   - `backend/best.pt` (PyTorch model)
   - `backend/best.quant.onnx` (Quantized ONNX model)

2. **Copy them** to the new PC's `backend/` folder

3. Models are large (50-500 MB), so plan accordingly for transfer

## Configuration for Different Network Setup

If deploying on a different network or with different IPs:

### For Local-Only Access (Same PC)
No changes needed - uses localhost.

### For LAN Access (Other PCs on same network)

1. **Find your PC's IP address**:
   ```powershell
   ipconfig
   # Look for IPv4 Address (e.g., 192.168.1.100)
   ```

2. **Update CORS in backend/main.py**:
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=[
           "http://localhost:8001",
           "http://192.168.1.100:8001"  # Add your IP
       ],
       ...
   )
   ```

3. **Update frontend config** in `frontend/config.js` (if exists) or `frontend/script.js`:
   ```javascript
   const API_URL = 'http://192.168.1.100:8000';
   ```

4. **Allow through Windows Firewall**:
   - Windows Settings → Privacy & Security → Windows Firewall
   - Allow Python through firewall for private networks

## Virtual Environment (Recommended for Isolation)

For a cleaner setup, use a virtual environment:

```powershell
# Create virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\Activate.ps1

# Install dependencies
cd backend
pip install -r requirements.txt

# Run the application
cd ..
.\restart.ps1
```

## Docker Deployment (Alternative)

If Docker is available, you can containerize:

```powershell
# Build the backend container
cd backend
docker build -t yolo-backend .

# Run the container
docker run -p 8000:8000 yolo-backend
```

## Cloud Deployment Options

### Option 1: Render.com
- See `RENDER_DEPLOYMENT_GUIDE.md` for details
- Free tier available
- Automatic HTTPS

### Option 2: Heroku
- Similar to Render
- Requires Procfile

### Option 3: AWS/Azure/GCP
- More complex but scalable
- Requires container or VM setup

## Troubleshooting New Deployment

### Issue: "Python is not recognized"
**Solution**: 
- Reinstall Python with "Add to PATH" checked
- Or manually add Python to system PATH

### Issue: "Port already in use"
**Solution**:
```powershell
# Find what's using the port
netstat -ano | findstr :8000

# Kill that process
taskkill /PID <PID> /F

# Or change port in config files
```

### Issue: "Model file not found"
**Solution**:
- Ensure `best.pt` or `best.quant.onnx` is in `backend/`
- Check file permissions

### Issue: "Module not found" errors
**Solution**:
```powershell
# Reinstall all dependencies
cd backend
pip install --upgrade -r requirements.txt
```

### Issue: Frontend can't connect to backend
**Solution**:
1. Check both services are running
2. Verify CORS settings in backend/main.py
3. Check browser console for errors
4. Ensure firewall allows connections

## Quick Deployment Checklist

- [ ] Python 3.8+ installed
- [ ] Project files transferred
- [ ] Model files in backend/
- [ ] Run `setup.ps1` successfully
- [ ] Run `restart.ps1`
- [ ] Access http://localhost:8001
- [ ] Test with sample upload

## Performance Optimization for New PC

### For Faster Inference:
1. Use `best.quant.onnx` (quantized model)
2. Ensure adequate RAM (16GB+)
3. Use SSD for outputs folder
4. Close unnecessary background apps

### For Large Datasets:
1. Increase system page file
2. Monitor disk space (results can be large)
3. Clear `backend/outputs/` periodically

## Backup and Maintenance

### Regular Backups:
- Model files (`backend/*.pt`, `backend/*.onnx`)
- Configuration files (`backend/main.py`)
- History data (`history_data.json`)
- Custom modifications

### Updates:
```powershell
# Update Python packages
pip install --upgrade -r backend/requirements.txt

# Update YOLO/Ultralytics
pip install --upgrade ultralytics
```

## Security Considerations for Production

⚠️ This setup is designed for local/development use. For production:

1. **Add authentication** to API endpoints
2. **Use HTTPS** (not HTTP)
3. **Restrict CORS** to specific domains
4. **Limit upload sizes** and file types
5. **Add rate limiting**
6. **Use environment variables** for secrets
7. **Enable logging** and monitoring

## Getting Help

If you encounter issues:
1. Check `SETUP_GUIDE.md` for detailed instructions
2. Review logs in PowerShell console
3. Check `backend/outputs/` for error logs
4. Verify all prerequisites are installed
5. Try the manual setup process instead of automated
