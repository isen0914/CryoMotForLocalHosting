# CRYOMOT Deployment Guide for Render

## Project Structure
- **Backend**: FastAPI + YOLO model (Python)
- **Frontend**: Static HTML/CSS/JavaScript

## Prerequisites
1. GitHub account
2. Render account (sign up at https://render.com)
3. Git installed on your computer

---

## Part 1: Push Your Code to GitHub

### Step 1: Create GitHub Repository
1. Go to https://github.com/new
2. Name: `cryomot` (or your preferred name)
3. Set to **Public** or **Private** (both work with Render)
4. Don't initialize with README (your project already has files)
5. Click "Create repository"

### Step 2: Push Your Code
Open PowerShell in your project folder and run:

```powershell
# Initialize git if not already done
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit for Render deployment"

# Add your GitHub repository (replace YOUR_USERNAME and YOUR_REPO)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

# Push to GitHub
git branch -M main
git push -u origin main
```

---

## Part 2: Deploy Backend on Render

### Step 1: Create Web Service
1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Select your `cryomot` repository

### Step 2: Configure Backend Service
Fill in the following settings:

**Basic Settings:**
- **Name**: `cryomot-backend` (or your choice)
- **Region**: Choose closest to you
- **Branch**: `main`
- **Root Directory**: `backend`
- **Runtime**: `Docker`
- **Dockerfile Path**: `./Dockerfile`

**Build Settings:**
- **Docker Context**: `..` (parent directory)
- **Docker Command**: Leave empty (uses Dockerfile CMD)

**Instance Type:**
- Select **Free** (512MB RAM, spins down after 15 min of inactivity)

**Environment Variables:**
Click "Add Environment Variable" and add:
- Key: `PYTHONUNBUFFERED`, Value: `1`

### Step 3: Deploy Backend
1. Click **"Create Web Service"**
2. Wait for deployment (5-15 minutes)
3. Once deployed, you'll see a URL like: `https://cryomot-backend-xxxx.onrender.com`
4. **SAVE THIS URL** - you'll need it for the frontend!

### Step 4: Test Backend
Visit your backend URL in a browser. You should see the FastAPI docs page.

---

## Part 3: Deploy Frontend on Render

### Step 1: Update Frontend Config
Before deploying, update the backend URL in your frontend:

1. Open `frontend/config.js`
2. Replace the PRODUCTION URL with your actual backend URL:
```javascript
PRODUCTION: "https://cryomot-backend-xxxx.onrender.com",
```

3. Commit and push this change:
```powershell
git add frontend/config.js
git commit -m "Update backend URL for production"
git push
```

### Step 2: Create Static Site
1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Static Site"**
3. Select your `cryomot` repository

### Step 3: Configure Frontend Service
Fill in the following settings:

**Basic Settings:**
- **Name**: `cryomot-frontend` (or your choice)
- **Branch**: `main`
- **Root Directory**: `frontend`
- **Build Command**: Leave empty (static files don't need building)
- **Publish Directory**: `.` (current directory)

### Step 4: Deploy Frontend
1. Click **"Create Static Site"**
2. Wait for deployment (1-2 minutes)
3. Once deployed, you'll get a URL like: `https://cryomot-frontend.onrender.com`

---

## Part 4: Test Your Deployed Application

1. Visit your frontend URL: `https://cryomot-frontend.onrender.com`
2. Open browser console (F12) to check for errors
3. Try uploading a ZIP file to test the connection
4. If backend is "cold", first request may take 30-60 seconds (free tier limitation)

---

## Important Notes

### Free Tier Limitations
- **Backend**: Spins down after 15 min of inactivity
- **First request after sleep**: 30-60 second delay
- **Monthly hours**: 750 hours free (enough for hobby use)
- **RAM**: 512MB (should be sufficient for small models)

### Model Size Warning
If your YOLO model files are very large (>500MB), deployment may fail or be slow. Consider:
1. Using the quantized ONNX model instead of PyTorch .pt
2. Uploading model files separately via Render dashboard
3. Using external storage (AWS S3) for models

### CORS Configuration
Your backend already has CORS enabled (`allow_origins=["*"]`), which allows the frontend to connect.

---

## Troubleshooting

### Backend won't start
- Check deployment logs in Render dashboard
- Verify model files (`best.pt` or `best.quant.onnx`) are in backend folder
- Check Dockerfile path is correct

### Frontend can't connect to backend
1. Check browser console for CORS errors
2. Verify `config.js` has correct backend URL
3. Test backend URL directly in browser
4. Wait 60 seconds for cold backend to wake up

### Build fails
- Check that all required files are pushed to GitHub
- Verify `requirements.txt` has all dependencies
- Check Dockerfile syntax

---

## Updating Your Deployment

After making changes:

```powershell
# Commit your changes
git add .
git commit -m "Your update description"
git push

# Render will auto-deploy the changes
```

---

## Custom Domain (Optional)

Both services support custom domains:
1. Go to your service in Render dashboard
2. Click "Settings" → "Custom Domain"
3. Add your domain and configure DNS

---

## Monitoring

- **Logs**: View in Render dashboard under "Logs" tab
- **Metrics**: See request count, response times in dashboard
- **Alerts**: Set up email alerts for service failures

---

## Cost Optimization Tips

1. Use quantized ONNX model instead of PyTorch
2. Implement request caching for common queries
3. Consider upgrading to paid tier ($7/month) for always-on service
4. Use Render's sleep schedule if you only need it during certain hours

---

## Support

- Render Docs: https://render.com/docs
- Community: https://community.render.com
- GitHub Issues: Create issues in your repository

---

Good luck with your deployment! 🚀
