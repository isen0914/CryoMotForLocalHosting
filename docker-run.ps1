param(
    [switch]$BuildOnly
)

Write-Host "Building Docker image 'yolo-backend'..."
docker build -t yolo-backend .

if ($BuildOnly) { Write-Host "Build complete (exit)."; exit }

# Try to produce a docker-friendly forward-slash path for the host file
$pwdForward = (Get-Location).Path -replace '\\','/'
$hostModelPath = "$pwdForward/backend/best.pt"

Write-Host "Running Docker container and mounting: $hostModelPath -> /app/best.pt"
docker run -p 8000:8000 -v "$hostModelPath:/app/best.pt" yolo-backend
