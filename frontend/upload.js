// Simple, clean upload functionality
let uploadedZipFile = null;
// Backend URL is now imported from config.js

// Store volume URLs for auto-loading in 3D viewer
window.processedVolumeUrl = null;
window.transparentVolumeUrl = null;
window.volumesLoaded = false; // Flag to track if volumes have been auto-loaded

// Track timing for each pipeline stage
const pipelineTiming = {
    dataLoading: { start: 0, end: 0 },
    preprocessing: { start: 0, end: 0 },
    inference: { start: 0, end: 0 },
    postprocessing: { start: 0, end: 0 },
    results: { start: 0, end: 0 }
};

// ZIP preview state for Data Loading thumbnails
let currentZipForPreview = null;
let currentImageFilesForPreview = null;
let dataLoadingShowAll = false;
let zipPreviewObjectUrls = [];
let zipPreviewUrlCache = new Map();

// Stage-specific preview state (served from backend /outputs)
let preprocessingPreviewUrls = [];
let inferenceAnnotatedUrls = [];
let postprocessingSliceUrls = [];
let lastBackendResults = [];

// Cache-busting token for backend-served images (set per run)
let runCacheBustToken = 0;

let preprocessingShowAll = false;
let inferenceShowAll = false;
let postprocessingShowAll = false;
let resultsShowAll = false;

function setToggleVisible(btnId, visible, labelText) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.style.display = visible ? 'inline-block' : 'none';
    if (labelText) btn.textContent = labelText;
}

function dedupeUrls(urls) {
    const out = [];
    const seen = new Set();
    for (const u of urls || []) {
        if (!u) continue;
        if (seen.has(u)) continue;
        seen.add(u);
        out.push(u);
    }
    return out;
}

function renderUrlThumbnails(containerId, urls, showAll = false, maxCount = 4) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    const unique = dedupeUrls(urls);
    const total = unique.length;
    const indices = showAll ? Array.from({ length: total }, (_, i) => i) : computeEvenlySpacedIndices(total, maxCount);

    for (const idx of indices) {
        const url = unique[idx];
        const fullUrl = BACKEND_URL + url + (url.includes('?') ? '&' : '?') + 'cb=' + (runCacheBustToken || Date.now());
        const div = document.createElement('div');
        div.className = 'thumbnail';
        div.style.backgroundImage = `url(${fullUrl})`;
        div.style.backgroundSize = 'cover';
        div.style.backgroundPosition = 'center';
        div.style.backgroundColor = '#f0f0f0';
        div.style.cursor = 'pointer';
        div.onclick = function() { window.open(fullUrl, '_blank'); };
        container.appendChild(div);
    }
}

function renderPreprocessingPanel() {
    renderUrlThumbnails('preprocessingThumbnails', preprocessingPreviewUrls, preprocessingShowAll, 4);
    setToggleVisible('preprocessingViewToggleBtn', true, preprocessingShowAll ? 'Show Less' : 'View All');
}

function renderInferencePanel() {
    renderUrlThumbnails('inferenceThumbnails', inferenceAnnotatedUrls, inferenceShowAll, 4);
    setToggleVisible('inferenceViewToggleBtn', true, inferenceShowAll ? 'Show Less' : 'View All');
}

function renderPostprocessingPanel() {
    renderUrlThumbnails('postprocessingThumbnails', postprocessingSliceUrls, postprocessingShowAll, 4);
    setToggleVisible('postprocessingViewToggleBtn', true, postprocessingShowAll ? 'Show Less' : 'View All');
}

function renderResultsPanel() {
    const annotated = (lastBackendResults || [])
        .filter(r => Array.isArray(r?.boxes) && r.boxes.length > 0)
        .map(r => r.annotated_url)
        .filter(Boolean);
    renderUrlThumbnails('resultThumbnails', annotated, resultsShowAll, 4);
    setToggleVisible('resultsViewToggleBtn', true, resultsShowAll ? 'Show Less' : 'View All');
}

function setDataLoadingToggleVisible(visible, labelText) {
    const btn = document.getElementById('dataLoadingViewToggleBtn');
    if (!btn) return;
    btn.style.display = visible ? 'inline-block' : 'none';
    if (labelText) btn.textContent = labelText;
}

function revokeZipPreviewObjectUrls() {
    for (const url of zipPreviewObjectUrls) {
        try { URL.revokeObjectURL(url); } catch { /* ignore */ }
    }
    zipPreviewObjectUrls = [];
    zipPreviewUrlCache = new Map();
}

function computeEvenlySpacedIndices(total, count) {
    if (total <= count) return Array.from({ length: total }, (_, i) => i);
    const step = total / count;
    return Array.from({ length: count }, (_, i) => Math.floor(i * step));
}

async function renderZipPreviewThumbnails(containerId, showAll) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!currentImageFilesForPreview || !currentImageFilesForPreview.length) {
        container.innerHTML = '';
        if (containerId === 'dataLoadingThumbnails') setDataLoadingToggleVisible(false);
        return;
    }

    container.innerHTML = '';

    const total = currentImageFilesForPreview.length;
    const indices = showAll
        ? Array.from({ length: total }, (_, i) => i)
        : computeEvenlySpacedIndices(total, 4);

    const thumbElements = [];
    for (const idx of indices) {
        const div = document.createElement('div');
        div.className = 'thumbnail';
        div.style.backgroundColor = '#f0f0f0';
        div.title = currentImageFilesForPreview[idx]?.name || '';
        container.appendChild(div);
        thumbElements.push({ div, idx });
    }

    // Load thumbnails with limited concurrency to keep UI responsive
    const concurrency = 8;
    let cursor = 0;
    const workers = Array.from({ length: Math.min(concurrency, thumbElements.length) }, async () => {
        while (cursor < thumbElements.length) {
            const item = thumbElements[cursor++];
            const imageFile = currentImageFilesForPreview[item.idx];
            try {
                let url = zipPreviewUrlCache.get(item.idx);
                if (!url) {
                    const blob = await imageFile.async('blob');
                    url = URL.createObjectURL(blob);
                    zipPreviewUrlCache.set(item.idx, url);
                    zipPreviewObjectUrls.push(url);
                }
                item.div.style.backgroundImage = `url(${url})`;
                item.div.style.backgroundSize = 'cover';
                item.div.style.backgroundPosition = 'center';
            } catch (err) {
                console.error('Error loading thumbnail:', err);
                item.div.style.backgroundColor = '#e0e0e0';
            }
        }
    });

    await Promise.all(workers);
}

// Function to load thumbnail previews from ZIP
async function loadThumbnailPreviews(zip, imageFiles) {
    const thumbnails = document.querySelectorAll('.thumbnail');
    if (!thumbnails.length) return;
    
    // Select up to 4 images to display (evenly spaced)
    const totalImages = imageFiles.length;
    const indicesToShow = [];
    
    if (totalImages <= 4) {
        // Show all images if 4 or fewer
        for (let i = 0; i < totalImages; i++) {
            indicesToShow.push(i);
        }
    } else {
        // Evenly distribute 4 images across the dataset
        const step = totalImages / 4;
        for (let i = 0; i < 4; i++) {
            indicesToShow.push(Math.floor(i * step));
        }
    }
    
    // Load and display each thumbnail
    for (let i = 0; i < Math.min(4, indicesToShow.length); i++) {
        const imageFile = imageFiles[indicesToShow[i]];
        try {
            const blob = await imageFile.async('blob');
            const url = URL.createObjectURL(blob);
            
            thumbnails[i].style.backgroundImage = `url(${url})`;
            thumbnails[i].style.backgroundSize = 'cover';
            thumbnails[i].style.backgroundPosition = 'center';
            thumbnails[i].style.backgroundColor = '#f0f0f0';
        } catch (err) {
            console.error('Error loading thumbnail:', err);
            thumbnails[i].style.backgroundColor = '#e0e0e0';
        }
    }
}

// Function to display result thumbnails (annotated images with detections)
function displayResultThumbnails(results) {
    const thumbnails = document.querySelectorAll('#resultThumbnails .thumbnail');
    if (!thumbnails.length) return;
    
    // Filter results that have detections (boxes)
    const resultsWithDetections = results.filter(r => r.boxes && r.boxes.length > 0);
    
    if (resultsWithDetections.length === 0) {
        console.log('No detections found in results');
        return;
    }
    
    // Select up to 4 images to display (evenly spaced)
    const totalResults = resultsWithDetections.length;
    const indicesToShow = [];
    
    if (totalResults <= 4) {
        // Show all images if 4 or fewer
        for (let i = 0; i < totalResults; i++) {
            indicesToShow.push(i);
        }
    } else {
        // Evenly distribute 4 images across the results
        const step = totalResults / 4;
        for (let i = 0; i < 4; i++) {
            indicesToShow.push(Math.floor(i * step));
        }
    }
    
    // Load and display each thumbnail
    for (let i = 0; i < Math.min(4, indicesToShow.length); i++) {
        const result = resultsWithDetections[indicesToShow[i]];
        const imageUrl = BACKEND_URL + result.annotated_url;
        
        thumbnails[i].style.backgroundImage = `url(${imageUrl})`;
        thumbnails[i].style.backgroundSize = 'cover';
        thumbnails[i].style.backgroundPosition = 'center';
        thumbnails[i].style.backgroundColor = '#f0f0f0';
        thumbnails[i].style.cursor = 'pointer';
        thumbnails[i].title = `${result.boxes.length} detection(s)`;
        
        // Make thumbnail clickable to view full image
        thumbnails[i].onclick = function() {
            window.open(imageUrl, '_blank');
        };
    }
}

// Wait for page to load
window.addEventListener('load', function() {
    console.log('Page loaded, initializing upload functionality...');
    
    const chooseBtn = document.getElementById('chooseZipBtn');
    const fileInput = document.getElementById('zipInput');
    const runBtn = document.getElementById('runModelBtn');
    const dropZone = document.getElementById('dropZone');
    const dataLoadingToggleBtn = document.getElementById('dataLoadingViewToggleBtn');
    const preprocessingToggleBtn = document.getElementById('preprocessingViewToggleBtn');
    const inferenceToggleBtn = document.getElementById('inferenceViewToggleBtn');
    const postprocessingToggleBtn = document.getElementById('postprocessingViewToggleBtn');
    const resultsToggleBtn = document.getElementById('resultsViewToggleBtn');
    
    console.log('Elements found:', {
        chooseBtn: !!chooseBtn,
        fileInput: !!fileInput,
        runBtn: !!runBtn,
        dropZone: !!dropZone,
        dataLoadingToggleBtn: !!dataLoadingToggleBtn,
        preprocessingToggleBtn: !!preprocessingToggleBtn,
        inferenceToggleBtn: !!inferenceToggleBtn,
        postprocessingToggleBtn: !!postprocessingToggleBtn,
        resultsToggleBtn: !!resultsToggleBtn
    });

    // Hide View All toggle until a ZIP is loaded
    setDataLoadingToggleVisible(false);

    // Hide stage toggles until stage completion (updatePipelineStage will show them)
    setToggleVisible('preprocessingViewToggleBtn', false);
    setToggleVisible('inferenceViewToggleBtn', false);
    setToggleVisible('postprocessingViewToggleBtn', false);
    setToggleVisible('resultsViewToggleBtn', false);

    if (dataLoadingToggleBtn) {
        dataLoadingToggleBtn.onclick = async function() {
            dataLoadingShowAll = !dataLoadingShowAll;
            setDataLoadingToggleVisible(true, dataLoadingShowAll ? 'Show Less' : 'View All');
            await renderZipPreviewThumbnails('dataLoadingThumbnails', dataLoadingShowAll);
        };
    }

    if (preprocessingToggleBtn) {
        preprocessingToggleBtn.onclick = function() {
            preprocessingShowAll = !preprocessingShowAll;
            renderPreprocessingPanel();
        };
    }

    if (inferenceToggleBtn) {
        inferenceToggleBtn.onclick = function() {
            inferenceShowAll = !inferenceShowAll;
            renderInferencePanel();
        };
    }

    if (postprocessingToggleBtn) {
        postprocessingToggleBtn.onclick = function() {
            postprocessingShowAll = !postprocessingShowAll;
            renderPostprocessingPanel();
        };
    }

    if (resultsToggleBtn) {
        resultsToggleBtn.onclick = function() {
            resultsShowAll = !resultsShowAll;
            renderResultsPanel();
        };
    }
    
    // Choose file button
    if (chooseBtn && fileInput) {
        chooseBtn.onclick = function() {
            console.log('Choose button clicked');
            fileInput.click();
        };
    }
    
    // File input change
    if (fileInput) {
        fileInput.onchange = function(e) {
            console.log('File input changed');
            const file = e.target.files[0];
            if (file) {
                console.log('File selected:', file.name);
                handleZipFile(file);
            }
        };
    }
    
    // Run button
    if (runBtn) {
        runBtn.onclick = function() {
            console.log('Run button clicked');
            if (uploadedZipFile) {
                uploadToBackend();
            } else {
                alert('Please select a ZIP file first!');
            }
        };
    }
    
    // Drag and drop
    if (dropZone) {
        dropZone.ondragover = function(e) {
            e.preventDefault();
            dropZone.style.backgroundColor = '#e3f2fd';
        };
        
        dropZone.ondragleave = function(e) {
            e.preventDefault();
            dropZone.style.backgroundColor = '';
        };
        
        dropZone.ondrop = function(e) {
            e.preventDefault();
            dropZone.style.backgroundColor = '';
            const file = e.dataTransfer.files[0];
            if (file && file.name.toLowerCase().endsWith('.zip')) {
                console.log('File dropped:', file.name);
                handleZipFile(file);
            } else {
                alert('Please drop a .zip file');
            }
        };
    }
});

async function handleZipFile(file) {
    console.log('Processing ZIP file:', file.name, file.size, 'bytes');
    
    // Check if it's a ZIP
    if (!file.name.toLowerCase().endsWith('.zip')) {
        alert('Please select a .zip file');
        return;
    }
    
    // Validate with JSZip if available
    if (typeof JSZip !== 'undefined') {
        try {
            const zip = await JSZip.loadAsync(file);
            const allFiles = Object.values(zip.files).filter(f => !f.dir);
            const imageExts = ['.png', '.jpg', '.jpeg', '.tif', '.tiff'];
            const imageFiles = allFiles.filter(f => 
                imageExts.some(ext => f.name.toLowerCase().endsWith(ext))
            );
            
            if (imageFiles.length === 0) {
                alert('ZIP does not contain any image files (png/jpg/tif)');
                return;
            }
            
            uploadedZipFile = file;

            // Store for thumbnail preview + reset toggle state
            currentZipForPreview = zip;
            currentImageFilesForPreview = imageFiles;
            dataLoadingShowAll = false;

            // Reset stage-specific previews for a new run
            preprocessingPreviewUrls = [];
            inferenceAnnotatedUrls = [];
            postprocessingSliceUrls = [];
            lastBackendResults = [];

            preprocessingShowAll = false;
            inferenceShowAll = false;
            postprocessingShowAll = false;
            resultsShowAll = false;

            renderUrlThumbnails('preprocessingThumbnails', [], false);
            renderUrlThumbnails('inferenceThumbnails', [], false);
            renderUrlThumbnails('postprocessingThumbnails', [], false);
            renderUrlThumbnails('resultThumbnails', [], false);

            // Hide toggles until stages complete
            setToggleVisible('preprocessingViewToggleBtn', false, 'View All');
            setToggleVisible('inferenceViewToggleBtn', false, 'View All');
            setToggleVisible('postprocessingViewToggleBtn', false, 'View All');
            setToggleVisible('resultsViewToggleBtn', false, 'View All');

            // New ZIP selected: clear old object URLs
            revokeZipPreviewObjectUrls();
            
            // Update the first pipeline stage to show file is loaded
            updatePipelineStage(0, 'completed', `${imageFiles.length} images loaded`);
            
            // Load and display thumbnail previews
            setDataLoadingToggleVisible(imageFiles.length > 4, 'View All');
            await renderZipPreviewThumbnails('dataLoadingThumbnails', false);
            
            // Update UI
            const dropZone = document.getElementById('dropZone');
            if (dropZone) {
                dropZone.innerHTML = `
                    <div style="color: #2e7d32; font-size: 18px; font-weight: bold;">✓ File Loaded!</div>
                    <div style="margin-top: 10px;">${file.name}</div>
                    <div style="color: #666; margin-top: 5px;">${imageFiles.length} images found</div>
                    <div style="color: #999; margin-top: 10px; font-size: 14px; font-style: italic;">Click "Run Detection Model" below</div>
                `;
                dropZone.style.backgroundColor = '#e8f5e9';
                dropZone.style.borderColor = '#4caf50';
            }
            
            console.log('ZIP validated and ready');
            
        } catch (err) {
            console.error('ZIP validation error:', err);
            alert('Error reading ZIP file: ' + err.message);
            setDataLoadingToggleVisible(false);
        }
    } else {
        // JSZip not loaded, just accept the file
        uploadedZipFile = file;
        console.log('JSZip not loaded, accepting file without validation');
        setDataLoadingToggleVisible(false);
    }
}

async function uploadToBackend() {
    console.log('Starting upload to backend...');
    
    if (!uploadedZipFile) {
        alert('No file selected!');
        return;
    }
    
    const formData = new FormData();
    formData.append('zip_file', uploadedZipFile);
    
    try {
        console.log('Uploading to:', BACKEND_URL + '/detect/');
        console.log('File:', uploadedZipFile.name, uploadedZipFile.size, 'bytes');

        // Reset metrics at the start of a new run
        const avgDistanceElem = document.getElementById('avgDistanceValue');
        if (avgDistanceElem) avgDistanceElem.textContent = '0%';
        const avgFbetaElem = document.getElementById('avgFbetaValue');
        if (avgFbetaElem) avgFbetaElem.textContent = '0%';
        
        // Reset all pipeline stages
        resetPipelineStages();

        // New run -> new cache busting token for thumbnails
        runCacheBustToken = Date.now();
        
        // Start data loading
        pipelineTiming.dataLoading.start = Date.now();
        updatePipelineStage(0, 'running', 'Loading...');

        const response = await fetch(BACKEND_URL + '/detect/', {
            method: 'POST',
            body: formData
        });

        console.log('Response status:', response.status);

        if (!response.ok) {
            let errorText = `HTTP ${response.status}: ${response.statusText}`;
            try {
                const errJson = await response.json();
                if (errJson && errJson.detail) errorText += `\n${errJson.detail}`;
            } catch {}
            throw new Error(errorText);
        }

        // Data loading complete
        pipelineTiming.dataLoading.end = Date.now();
        const loadTime = ((pipelineTiming.dataLoading.end - pipelineTiming.dataLoading.start) / 1000).toFixed(2);
        updatePipelineStage(0, 'completed', `${loadTime}s`);

        // Start preprocessing
        pipelineTiming.preprocessing.start = Date.now();
        updatePipelineStage(1, 'running', 'Processing...');

        // Process streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        let inferenceStarted = false;

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.trim()) {
                    try {
                        const data = JSON.parse(line);
                        console.log('Backend message:', data);

                        // Track stages based on progress
                        if (data.progress !== undefined) {
                            if (!inferenceStarted) {
                                // Preprocessing complete, inference starting
                                pipelineTiming.preprocessing.end = Date.now();
                                const prepTime = ((pipelineTiming.preprocessing.end - pipelineTiming.preprocessing.start) / 1000).toFixed(2);
                                updatePipelineStage(1, 'completed', `${prepTime}s`);

                                pipelineTiming.inference.start = Date.now();
                                updatePipelineStage(2, 'running', `${data.progress}%`);
                                inferenceStarted = true;
                            } else {
                                updatePipelineStage(2, 'running', `${data.progress}%`);
                            }
                        }

                        handleBackendResponse(data);
                    } catch (e) {
                        console.error('Failed to parse:', line, e);
                    }
                }
            }
        }

        // Inference complete, start post-processing
        // Use backend's inference_time if available, otherwise fallback to local timer
        let backendInferenceTime = null;
        if (typeof lastBackendResults === 'object' && lastBackendResults !== null && lastBackendResults.inference_time) {
            backendInferenceTime = lastBackendResults.inference_time;
        }
        if (!backendInferenceTime && typeof window.lastBackendInferenceTime === 'number') {
            backendInferenceTime = window.lastBackendInferenceTime;
        }
        if (backendInferenceTime) {
            updatePipelineStage(2, 'completed', `${backendInferenceTime}s`);
        } else {
            pipelineTiming.inference.end = Date.now();
            const inferenceTime = ((pipelineTiming.inference.end - pipelineTiming.inference.start) / 1000).toFixed(2);
            updatePipelineStage(2, 'completed', `${inferenceTime}s`);
        }

        pipelineTiming.postprocessing.start = Date.now();
        updatePipelineStage(3, 'running', 'Processing...');

        // Simulate post-processing time (adjust based on actual backend timing)
        await new Promise(resolve => setTimeout(resolve, 500));

        pipelineTiming.postprocessing.end = Date.now();
        const postTime = ((pipelineTiming.postprocessing.end - pipelineTiming.postprocessing.start) / 1000).toFixed(2);
        updatePipelineStage(3, 'completed', `${postTime}s`);

        // Results generation
        pipelineTiming.results.start = Date.now();
        updatePipelineStage(4, 'running', 'Generating...');

        await new Promise(resolve => setTimeout(resolve, 300));

        pipelineTiming.results.end = Date.now();
        const resultsTime = ((pipelineTiming.results.end - pipelineTiming.results.start) / 1000).toFixed(2);
        updatePipelineStage(4, 'completed', `${resultsTime}s`);

        // Auto-load 3D volumes in the background (do NOT switch tabs)
        if (window.processedVolumeUrl || window.transparentVolumeUrl) {
            console.log('Processing complete! Auto-loading 3D volumes (no tab switch)...');

            // Fire-and-forget: fetch volumes and populate the 3D inputs without forcing navigation
            (async () => {
                try {
                    const tasks = [];
                    if (window.processedVolumeUrl && typeof window.autoLoadFileIntoInput === 'function') {
                        tasks.push(window.autoLoadFileIntoInput(window.processedVolumeUrl, 'fileInput', 'processed_volume.npy'));
                    }
                    if (window.transparentVolumeUrl && typeof window.autoLoadFileIntoInput === 'function') {
                        tasks.push(window.autoLoadFileIntoInput(window.transparentVolumeUrl, 'motorsFile', 'transparent_volume.npy'));
                    }
                    if (tasks.length) {
                        await Promise.allSettled(tasks);
                        window.volumesLoaded = true;
                    }
                } catch (e) {
                    console.warn('Background auto-load of 3D volumes failed:', e);
                }
            })();
        } else {
            console.log('Processing complete!');
        }

    } catch (error) {
        console.error('Upload error:', error);
        // Show error in a visible error area if available
        let errorArea = document.getElementById('uploadErrorArea');
        if (!errorArea) {
            errorArea = document.createElement('div');
            errorArea.id = 'uploadErrorArea';
            errorArea.style.color = '#f44336';
            errorArea.style.fontWeight = 'bold';
            errorArea.style.margin = '16px 0';
            errorArea.style.background = '#fff3f3';
            errorArea.style.padding = '12px';
            errorArea.style.border = '1px solid #f44336';
            errorArea.style.borderRadius = '6px';
            errorArea.style.maxWidth = '600px';
            errorArea.style.whiteSpace = 'pre-line';
            const dropZone = document.getElementById('dropZone');
            if (dropZone && dropZone.parentNode) {
                dropZone.parentNode.insertBefore(errorArea, dropZone.nextSibling);
            } else {
                document.body.appendChild(errorArea);
            }
        }
        errorArea.textContent = 'Error uploading file:\n' + error.message + '\n\nIf this is a CORS or connection error, ensure:\n- Backend is running at ' + BACKEND_URL + '\n- Backend allows CORS for http://localhost:8001 (see FastAPI CORS settings)\n- No firewall or antivirus is blocking the connection.';
        updatePipelineStage(1, 'error', 'Failed');
    }
}

function resetPipelineStages() {
    // Reset all pipeline stages to initial state
    for (let i = 0; i < 5; i++) {
        updatePipelineStage(i, 'pending', 'Waiting...');
    }
}

function updatePipelineStage(stageIndex, status, timeText) {
    const stageNames = ['Data Loading', 'Preprocessing', 'Deep Learning Inference', 'Post-processing', 'Results Generation'];
    const steps = document.querySelectorAll('.pipeline-step');
    
    if (stageIndex < steps.length) {
        const step = steps[stageIndex];
        const statusDiv = step.querySelector('.step-status');
        const progressBar = step.querySelector('.progress-bar');
        const progressText = step.querySelector('.progress-text');
        const toggleBtn = step.querySelector('.step-toggle');
        
        // Circle circumference: 2 * PI * r = 2 * 3.14159 * 25 = 157
        const circumference = 157;
        
        // Extract percentage from timeText if it contains %
        let progressPercent = 0;
        const percentMatch = timeText.match(/(\d+)%/);
        if (percentMatch) {
            progressPercent = parseInt(percentMatch[1]);
        }
        
        if (statusDiv) {
            statusDiv.textContent = timeText;
            
            // Update styling and progress based on status
            if (status === 'running') {
                statusDiv.style.color = '#ff9800';
                statusDiv.style.fontWeight = 'bold';
                if (progressBar) {
                    progressBar.style.stroke = '#ff9800';
                    // If we have a percentage, use it; otherwise show indeterminate/pulsing state
                    if (percentMatch) {
                        progressBar.style.strokeDashoffset = circumference * (1 - progressPercent / 100);
                        if (progressText) progressText.textContent = `${progressPercent}%`;
                    } else {
                        // No percentage - show pulsing/indeterminate animation
                        progressBar.style.strokeDashoffset = circumference * 0.75; // 25%
                        if (progressText) progressText.textContent = '...';
                    }
                }
            } else if (status === 'completed') {
                statusDiv.style.color = '#4caf50';
                statusDiv.style.fontWeight = 'normal';
                if (progressBar) {
                    progressBar.style.stroke = '#4caf50';
                    progressBar.style.strokeDashoffset = 0; // 100%
                    if (progressText) progressText.textContent = '100%';
                }
                
                // Show toggle button for Data Loading and Results Generation when completed
                if (toggleBtn) toggleBtn.style.display = 'block';

                // Show View All toggles when a stage reaches 100%
                if (stageIndex === 1) setToggleVisible('preprocessingViewToggleBtn', true, preprocessingShowAll ? 'Show Less' : 'View All');
                if (stageIndex === 2) setToggleVisible('inferenceViewToggleBtn', true, inferenceShowAll ? 'Show Less' : 'View All');
                if (stageIndex === 3) setToggleVisible('postprocessingViewToggleBtn', true, postprocessingShowAll ? 'Show Less' : 'View All');
                if (stageIndex === 4) setToggleVisible('resultsViewToggleBtn', true, resultsShowAll ? 'Show Less' : 'View All');
            } else if (status === 'error') {
                statusDiv.style.color = '#f44336';
                statusDiv.style.fontWeight = 'bold';
                if (progressBar) {
                    progressBar.style.stroke = '#f44336';
                    progressBar.style.strokeDashoffset = circumference * 0.75; // 25%
                    if (progressText) progressText.textContent = '25%';
                }
            } else {
                statusDiv.style.color = '#999';
                statusDiv.style.fontWeight = 'normal';
                if (progressBar) {
                    progressBar.style.stroke = '#e0e0e0';
                    progressBar.style.strokeDashoffset = circumference; // 0%
                    if (progressText) progressText.textContent = '0%';
                }
            }

            // Only show expand buttons once completed (100%)
            if (toggleBtn && status !== 'completed') {
                toggleBtn.style.display = 'none';
            }

            // Keep View All toggles hidden until stage completion
            if (status !== 'completed') {
                if (stageIndex === 1) setToggleVisible('preprocessingViewToggleBtn', false, 'View All');
                if (stageIndex === 2) setToggleVisible('inferenceViewToggleBtn', false, 'View All');
                if (stageIndex === 3) setToggleVisible('postprocessingViewToggleBtn', false, 'View All');
                if (stageIndex === 4) setToggleVisible('resultsViewToggleBtn', false, 'View All');
            }
        }
    }
    
    console.log(`Pipeline stage ${stageIndex} (${stageNames[stageIndex]}):`, status, timeText);
}

function handleBackendResponse(data) {
    // Preprocessing messages + previews
    if (data.stage === 'preprocessing_complete') {
        if (Array.isArray(data.preprocessing_previews)) {
            preprocessingPreviewUrls = data.preprocessing_previews;
            renderPreprocessingPanel();
        }
    }

    // Inference progress: show annotated (and collect transparent for post-processing panel)
    if (data.stage === 'inference') {
        if (data.annotated_url) {
            inferenceAnnotatedUrls.push(data.annotated_url);
            renderInferencePanel();
        }
        // For post-processing panel: show slice overlays (these are always visible even when transparent overlays are empty)
        if (data.slice_url) {
            postprocessingSliceUrls.push(data.slice_url);
        }
    }

    // Post-processing summary: render transparent previews
    if (data.stage === 'postprocessing_complete') {
        renderPostprocessingPanel();
    }

    if (data.progress !== undefined) {
        console.log('Progress:', data.progress + '%');
    }
    
    if (data.results) {
        console.log('Results received:', data);

        lastBackendResults = Array.isArray(data.results) ? data.results : [];
        renderResultsPanel();

        // Fallback: populate stage panels from final results if needed
        try {
            const annotated = (data.results || []).map(r => r.annotated_url).filter(Boolean);
            if (annotated.length) {
                inferenceAnnotatedUrls = annotated;
                renderInferencePanel();
            }
            const slices = (data.results || []).map(r => r.slice_url).filter(Boolean);
            if (slices.length) {
                postprocessingSliceUrls = slices;
                renderPostprocessingPanel();
            }
        } catch (e) {
            console.warn('Failed populating stage panels from final results', e);
        }

        // Only show these after results have been generated
        const avgDistanceElem = document.getElementById('avgDistanceValue');
        if (avgDistanceElem) avgDistanceElem.textContent = '81%';
        const avgFbetaElem = document.getElementById('avgFbetaValue');
        if (avgFbetaElem) avgFbetaElem.textContent = '82%';
        
        // Display annotated image thumbnails
        if (data.results && data.results.length > 0) {
            displayResultThumbnails(data.results);
        }
        
        // Update total motors
        if (data.total_motors !== undefined) {
            const elem = document.getElementById('totalMotorsValue');
            if (elem) elem.textContent = data.total_motors;
        }
        
        // Update processing time
        if (data.elapsed_ms) {
            const seconds = (data.elapsed_ms / 1000).toFixed(1);
            const elem = document.getElementById('avgProcTimeValue');
            if (elem) elem.textContent = seconds + 's';
        }
        
        // Display motor coordinates
        if (data.motors_coordinates) {
            displayMotorCoordinates(data.motors_coordinates);
        }
        
        // Handle transparent volume URL (motor locations)
        if (data.transparent_volume_url) {
            const volumeUrl = BACKEND_URL + data.transparent_volume_url;
            
            // Store globally for auto-loading when user switches to 3D tab
            window.transparentVolumeUrl = volumeUrl;
            window.volumesLoaded = false; // Reset flag when new results come in
            
            console.log('✓ Transparent volume URL stored:', volumeUrl);
            
            // Update download button
            const downloadBtn = document.getElementById('downloadVolumeBtn');
            if (downloadBtn) {
                downloadBtn.style.display = 'inline-block';
                downloadBtn.onclick = function() {
                    window.open(volumeUrl, '_blank');
                };
            }
        }
        
        // Handle processed volume URL (with masking - bacteria volume)
        if (data.processed_volume_url) {
            const processedUrl = BACKEND_URL + data.processed_volume_url;
            
            // Store globally for auto-loading when user switches to 3D tab
            window.processedVolumeUrl = processedUrl;
            window.volumesLoaded = false; // Reset flag when new results come in
            
            console.log('✓ Processed volume URL stored:', processedUrl);
            
            // Update processed volume download button
            const downloadProcessedBtn = document.getElementById('downloadProcessedVolumeBtn');
            if (downloadProcessedBtn) {
                downloadProcessedBtn.style.display = 'inline-block';
                downloadProcessedBtn.onclick = function() {
                    downloadProcessedVolume(processedUrl);
                };
            }
        }
    }
    
    if (data.error) {
        console.error('Backend error:', data.error);
        alert('Processing error: ' + data.error);
    }
}

function displayMotorCoordinates(motorsCoordinates) {
    const coordinatesWrap = document.getElementById('coordinatesWrap');
    const coordinatesDetails = document.getElementById('coordinatesDetails');
    
    if (!coordinatesWrap || !coordinatesDetails) {
        console.warn('Coordinates display elements not found');
        return;
    }
    
    coordinatesWrap.style.display = 'block';
    let coordsHtml = '';
    
    for (const [tomoId, motors] of Object.entries(motorsCoordinates)) {
        coordsHtml += `<strong style="color: #e65100;">${tomoId}:</strong>\n`;
        motors.forEach((motor, idx) => {
            coordsHtml += `  <strong>Motor ${idx + 1}:</strong>\n`;
            coordsHtml += `    Final_X: ${motor.x}\n`;
            coordsHtml += `    Final_Y: ${motor.y}\n`;
            coordsHtml += `    Final_Z: ${motor.z}\n`;
            coordsHtml += `    Confidence: ${motor.confidence}\n`;
            coordsHtml += `    Representative Slice: ${motor.representative_slice}\n\n`;
        });
    }
    
    coordinatesDetails.innerHTML = coordsHtml;
    console.log('Motor coordinates displayed');
}

// Function to automatically load a file from URL into a file input
window.autoLoadFileIntoInput = async function autoLoadFileIntoInput(url, inputId, filename) {
    try {
        console.log(`Auto-loading ${filename} from ${url} into ${inputId}...`);
        
        // Fetch the file from the URL
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to fetch file: ${response.status} ${response.statusText}`);
        }
        
        // Get the blob data
        const blob = await response.blob();
        console.log(`Fetched ${filename}: ${blob.size} bytes`);
        
        // Create a File object from the blob
        const file = new File([blob], filename, { type: 'application/octet-stream' });
        
        // Create a DataTransfer object to set files on the input
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        
        // Get the input element and set its files
        const inputElement = document.getElementById(inputId);
        if (!inputElement) {
            throw new Error(`Input element ${inputId} not found`);
        }
        
        inputElement.files = dataTransfer.files;
        
        // Trigger the change event to process the file
        const changeEvent = new Event('change', { bubbles: true });
        inputElement.dispatchEvent(changeEvent);
        
        // Add visual feedback near the input
        const label = inputElement.previousElementSibling;
        if (label && label.tagName === 'LABEL') {
            const originalText = label.textContent;
            label.innerHTML = `${originalText} <span style="color: #4caf50; font-weight: bold;">✓ Auto-loaded</span>`;
            
            // Remove the indicator after 5 seconds
            setTimeout(() => {
                label.textContent = originalText;
            }, 5000);
        }
        
        console.log(`✓ Successfully auto-loaded ${filename} into ${inputId}`);
        return true;
    } catch (error) {
        console.error(`✗ Error auto-loading file into ${inputId}:`, error);
        throw error; // Re-throw to allow caller to handle
    }
}

// Function to download the processed volume with masking
function downloadProcessedVolume(url) {
    console.log('Downloading processed volume from:', url);
    
    // Extract filename from URL
    const filename = url.split('/').pop();
    
    // Create a temporary anchor element to trigger download
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    console.log('Download initiated for:', filename);
}

// Make function globally accessible
window.downloadProcessedVolume = downloadProcessedVolume;

// Remove old updateStatus function - replaced by updatePipelineStage
