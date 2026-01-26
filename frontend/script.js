// Global variable to track history refresh interval
let historyRefreshInterval = null;

// Global variables for backend integration
let lastUploadedZip = null;
// Backend URL is now imported from config.js
const backendUrl = BACKEND_URL;
let currentTransparentVolumeUrl = null;

// Debug: Verify script is loading
console.log('script.js loaded successfully');
console.log('Defining global functions...');

// Make functions globally accessible
window.switchTab = function switchTab(tabName) {
  console.log('switchTab called:', tabName);
  const sections = document.querySelectorAll('.section');
  sections.forEach((section) => section.classList.remove('active'));

  // Update active state for both desktop and mobile nav buttons
  const allButtons = document.querySelectorAll('.nav-btn');
  allButtons.forEach((btn) => btn.classList.remove('active'));

  const targetSection = document.getElementById(tabName);
  if (targetSection) {
    targetSection.classList.add('active');
  } else {
    console.error('Section not found:', tabName);
    return;
  }
  
  // Find and activate the corresponding buttons in both desktop and mobile nav
  const desktopButtons = document.querySelectorAll('#desktop-nav .nav-btn');
  const mobileButtons = document.querySelectorAll('.mobile-nav .nav-btn');
  
  desktopButtons.forEach((btn, index) => {
    if (btn.onclick && btn.onclick.toString().includes(`'${tabName}'`)) {
      btn.classList.add('active');
    }
  });
  
  mobileButtons.forEach((btn, index) => {
    if (btn.onclick && btn.onclick.toString().includes(`'${tabName}'`)) {
      btn.classList.add('active');
    }
  });

  // Handle history tab - fetch and start auto-refresh
  if (tabName === 'history') {
    loadHistory(); // Fetch immediately when tab is opened
    startHistoryAutoRefresh();
  } else {
    stopHistoryAutoRefresh();
  }
  
  // Handle visualization tab - auto-load volumes if available
  if (tabName === 'visualization') {
    // Force a VTK relayout/render once the tab is visible.
    // Without this, VTK can render while the tab is hidden (0x0) and only appears after a real window resize
    // (e.g., when opening DevTools responsive mode).
    try {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          window.dispatchEvent(new Event('resize'));
          if (typeof window.vtkForceResizeRender === 'function') {
            window.vtkForceResizeRender();
          }
        });
      });
    } catch (e) {
      console.warn('Failed to trigger VTK resize/render on tab switch:', e);
    }

    if ((window.processedVolumeUrl || window.transparentVolumeUrl) && !window.volumesLoaded) {
      // Show notification
      const notification = document.getElementById('autoLoadNotification');
      if (notification) {
        notification.style.display = 'block';
        notification.textContent = '⏳ Loading volumes automatically...';
        notification.style.background = '#ff9800';
      }
      
      setTimeout(() => {
        let loadedCount = 0;
        let failedCount = 0;
        const totalToLoad = (window.processedVolumeUrl ? 1 : 0) + (window.transparentVolumeUrl ? 1 : 0);
        
        if (window.processedVolumeUrl && typeof window.autoLoadFileIntoInput === 'function') {
          window.autoLoadFileIntoInput(window.processedVolumeUrl, 'fileInput', 'processed_volume.npy')
            .then(() => {
              loadedCount++;
              console.log('✓ Processed volume (bacteria) loaded successfully');
              if (loadedCount + failedCount === totalToLoad) {
                showResultNotification();
              }
            })
            .catch((error) => {
              failedCount++;
              console.error('✗ Failed to load processed volume:', error);
              if (loadedCount + failedCount === totalToLoad) {
                showResultNotification();
              }
            });
        }
        if (window.transparentVolumeUrl && typeof window.autoLoadFileIntoInput === 'function') {
          window.autoLoadFileIntoInput(window.transparentVolumeUrl, 'motorsFile', 'transparent_volume.npy')
            .then(() => {
              loadedCount++;
              console.log('✓ Transparent volume (motor locations) loaded successfully');
              if (loadedCount + failedCount === totalToLoad) {
                showResultNotification();
              }
            })
            .catch((error) => {
              failedCount++;
              console.error('✗ Failed to load transparent volume:', error);
              if (loadedCount + failedCount === totalToLoad) {
                showResultNotification();
              }
            });
        }
        
        function showResultNotification() {
          const notification = document.getElementById('autoLoadNotification');
          if (notification) {
            if (loadedCount === totalToLoad) {
              notification.textContent = `✓ ${loadedCount} volume(s) automatically loaded from detection results`;
              notification.style.background = '#4caf50';
            } else if (loadedCount > 0) {
              notification.textContent = `⚠ ${loadedCount}/${totalToLoad} volume(s) loaded (${failedCount} failed)`;
              notification.style.background = '#ff9800';
            } else {
              notification.textContent = `✗ Failed to load volumes automatically`;
              notification.style.background = '#f44336';
            }
            setTimeout(() => {
              notification.style.display = 'none';
            }, 5000);
          }
          window.volumesLoaded = true;
        }
      }, 300);
    }
  }
}

// Make other navigation functions globally accessible
window.toggleMobileNav = function toggleMobileNav() {
  const mobileNav = document.getElementById('mobileNav');
  const overlay = document.getElementById('mobileNavOverlay');
  
  mobileNav.classList.toggle('open');
  overlay.classList.toggle('show');
}

window.closeMobileNav = function closeMobileNav() {
  const mobileNav = document.getElementById('mobileNav');
  const overlay = document.getElementById('mobileNavOverlay');
  
  mobileNav.classList.remove('open');
  overlay.classList.remove('show');
}

window.toggleStep = function toggleStep(button) {
  const expanded = button.closest('div').nextElementSibling;
  if (expanded && expanded.classList.contains('step-content-expanded')) {
    expanded.classList.toggle('show');
    button.textContent = expanded.classList.contains('show') ? '▲' : '▼';
  }
}

window.toggleHistory = function toggleHistory(button) {
  const expanded = button.closest('div').parentElement.nextElementSibling;
  if (expanded && expanded.classList.contains('history-expanded')) {
    expanded.classList.toggle('show');
    button.textContent = expanded.classList.contains('show') ? '▲' : '▼';
  }
}

// Start auto-refresh for history (every 10 seconds)
function startHistoryAutoRefresh() {
  // Clear any existing interval first
  stopHistoryAutoRefresh();
  
  // Set up new interval
  historyRefreshInterval = setInterval(() => {
    console.log("Auto-refreshing history...");
    loadHistory();
  }, 10000); // 10 seconds
}

// Stop auto-refresh
function stopHistoryAutoRefresh() {
  if (historyRefreshInterval) {
    clearInterval(historyRefreshInterval);
    historyRefreshInterval = null;
  }
}

function openZipPicker() {
  const dropZone = document.querySelector('.drop-zone');
  
  // Reset dropzone if file was already loaded
  if (dropZone && dropZone.classList.contains('file-loaded')) {
    dropZone.classList.remove('file-loaded');
    dropZone.innerHTML = 'Drop a .zip containing tomogram images here';
    lastUploadedZip = null;
  }
  
  document.getElementById('zipInput').click();
}

function handleZipSelect(event) {
  console.log('handleZipSelect called', event);
  const file = event.target.files && event.target.files[0];
  console.log('File selected:', file);
  if (!file) {
    console.warn('No file selected');
    return;
  }
  processZipFile(file);
}

function handleDragOver(event) {
  event.preventDefault();
  event.stopPropagation();
  event.currentTarget.classList.add('dragover');
}

function handleDragLeave(event) {
  event.preventDefault();
  event.stopPropagation();
  event.currentTarget.classList.remove('dragover');
}

function handleDrop(event) {
  event.preventDefault();
  event.stopPropagation();
  event.currentTarget.classList.remove('dragover');

  const items = event.dataTransfer.items;
  if (items) {
    for (let i = 0; i < items.length; i++) {
      if (items[i].kind === 'file') {
        const entry = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
        if (entry && entry.isDirectory) {
          console.log('Folder dropped:', entry.name);
          alert(`Folder "${entry.name}" dropped successfully!`);
        }
      }
    }
  }
  const files = event.dataTransfer.files;
  if (!files || files.length === 0) return;
  // only accept a single .zip
  const file = files[0];
  if (!file.name.toLowerCase().endsWith('.zip')) {
    alert('Please drop a .zip file containing tomogram images.');
    return;
  }
  processZipFile(file);
}

// Format a Date to "MM-DD-YYYY HH:MM:SS"
function formatTimestamp(d) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}-${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// Save current Results into History (name = current date/time)
async function saveResult() {
  const name = formatTimestamp(new Date());

  const total = document.getElementById('totalMotorsValue')?.textContent?.trim() || '0';
  const avgProc = document.getElementById('avgProcTimeValue')?.textContent?.trim() || '';

  const high = document.getElementById('highConfCount')?.textContent?.trim() || '0';
  const med = document.getElementById('medConfCount')?.textContent?.trim() || '0';
  const low = document.getElementById('lowConfCount')?.textContent?.trim() || '0';

  // Save to local backend storage
  const data = {
    timestamp: name,
    total_motors: total,
    avg_proc_time: avgProc,
    high_conf: high,
    med_conf: med,
    low_conf: low
  };

  try {
    const response = await fetch(`${backendUrl}/api/history`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    const result = await response.json();

    // Give brief feedback on button
    const btn = document.getElementById('saveResultBtn');
    if (response.ok && !result.error) {
      await loadHistory(); // Reload history to show new entry
      if (btn) {
        const prev = btn.textContent;
        btn.textContent = '✅ Saved';
        setTimeout(() => (btn.textContent = prev), 1200);
      }
    } else {
      if (btn) {
        const prev = btn.textContent;
        btn.textContent = '❌ Error';
        setTimeout(() => (btn.textContent = prev), 1200);
      }
      console.error("Failed to save result:", result.error);
    }
  } catch (error) {
    const btn = document.getElementById('saveResultBtn');
    if (btn) {
      const prev = btn.textContent;
      btn.textContent = '❌ Error';
      setTimeout(() => (btn.textContent = prev), 1200);
    }
    console.error("Failed to save result:", error);
  }
}

// Delete a history entry. `btn` is the 'Delete' button inside .history-expanded
async function deleteHistory(btn) {
  const recordId = btn.getAttribute('data-id');
  
  if (!recordId) {
    console.warn('No record ID found');
    return;
  }

  try {
    const response = await fetch(`${backendUrl}/api/history/${recordId}`, {
      method: 'DELETE'
    });

    const result = await response.json();

    if (response.ok && !result.error) {
      await loadHistory(); // Reload history to reflect deletion
    } else {
      alert("Failed to delete record: " + (result.error || 'Unknown error'));
      console.error("Delete error:", result.error);
    }
  } catch (error) {
    alert("Failed to delete record: " + error.message);
    console.error("Delete error:", error);
  }
}

// ============ LOCAL FILE STORAGE DATABASE FUNCTIONS ============
// Load history from local backend storage
async function loadHistory() {
  try {
    const response = await fetch(`${backendUrl}/api/history`);
    const result = await response.json();
    
    console.log("Load history result:", result);
    
    let records = [];
    if (result.data) {
      records = result.data;
    } else if (Array.isArray(result)) {
      records = result;
    } else if (result.error) {
      console.warn("Failed to load history:", result.error);
      return;
    }

    const historyList = document.querySelector('.history-list');
    if (!historyList) {
      console.warn("History list element not found");
      return;
    }

    // Clear existing history items (keep the h2 title)
    const children = Array.from(historyList.children);
    children.forEach((child, index) => {
      if (index > 0) child.remove(); // Keep first child (h2 title)
    });

    console.log("Records to display:", records);

    // Populate with database records
    records.forEach(record => {
      const container = document.createElement('div');

      const item = document.createElement('div');
      item.className = 'history-item';
      item.innerHTML = `
        <div class="history-timestamp">${record.timestamp}</div>
        <div class="history-count">${record.total_motors}</div>
        <div class="history-controls">
          <button class="delete-btn" onclick="toggleHistory(this)">▼</button>
        </div>
      `;

      const expanded = document.createElement('div');
      expanded.className = 'history-expanded';
      expanded.innerHTML = `
        <div class="stats-grid" style="margin-top: 0">
          <div class="stat-box">
            <div class="stat-label">Total Motors Detected</div>
            <div class="stat-value">${record.total_motors}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Avg. Processing time</div>
            <div class="stat-value">${record.avg_proc_time}</div>
          </div>
        </div>
        <button class="delete-history-btn" data-id="${record.id}" onclick="deleteHistory(this)">Delete</button>
      `;

      container.appendChild(item);
      container.appendChild(expanded);
      historyList.appendChild(container);
    });
  } catch (error) {
    console.error("Failed to load history:", error);
  }
}

// Add random test data to database
// Add random test data to database
async function addRandomHistory() {
  const data = {
    timestamp: formatTimestamp(new Date()),
    total_motors: String(Math.floor(Math.random() * 10)),
    avg_proc_time: (Math.random() * 60).toFixed(1) + "s",
    high_conf: String(Math.floor(Math.random() * 5)),
    med_conf: String(Math.floor(Math.random() * 5)),
    low_conf: String(Math.floor(Math.random() * 5))
  };

  try {
    const response = await fetch(`${backendUrl}/api/history`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    const result = await response.json();
    
    if (response.ok && !result.error) {
      console.log("Insert successful, reloading history...");
      await loadHistory(); // Reload history to show new entry
      alert("Random test data added!");
    } else {
      alert("Failed to add test data: " + (result.error || 'Unknown error'));
    }
  } catch (error) {
    alert("Failed to add test data: " + error.message);
    console.error("Error:", error);
  }
}

// Process a ZIP file client-side using JSZip and validate image contents
async function processZipFile(file) {
  console.log('processZipFile called with file:', file.name, file.size, 'bytes');
  if (typeof JSZip === 'undefined') {
    console.error('JSZip is not loaded!');
    alert('JSZip is not loaded. Ensure the JSZip script is included.');
    return;
  }
  console.log('JSZip is available, processing...');

  try {
    const zip = await JSZip.loadAsync(file);
    const allFiles = Object.values(zip.files).filter(f => !f.dir);
    const imageExts = ['.png', '.jpg', '.jpeg', '.tif', '.tiff'];
    const imageFiles = allFiles.filter(f => imageExts.some(ext => f.name.toLowerCase().endsWith(ext)));

    if (imageFiles.length === 0) {
      alert('ZIP does not contain recognized image files (png/jpg/tif).');
      return;
    }

    lastUploadedZip = file;
    
    // Update dropzone to show file was accepted
    const dropZone = document.querySelector('.drop-zone');
    if (dropZone) {
      dropZone.innerHTML = `<div style="font-size: 18px; font-weight: 600; color: #2e7d32; margin-bottom: 8px;">\u2713 File loaded successfully!</div><div style="font-size: 14px; color: #555;">${file.name}</div><div style="font-size: 13px; color: #777; margin-top: 4px;">${imageFiles.length} images found</div><div style="font-size: 12px; color: #999; margin-top: 8px; font-style: italic;">Click "Run Detection Model" below to process</div>`;
      dropZone.classList.add('file-loaded');
    }
    
    console.log(`ZIP accepted: ${file.name} with ${imageFiles.length} images`);

  } catch (err) {
    console.error('ZIP processing error', err);
    alert('Failed to read ZIP: ' + err.message);
  }
}

// Cleanup: remove stray text nodes that contain only the character "2"
// NOTE: Upload functionality now handled by upload.js
document.addEventListener('DOMContentLoaded', () => {
  console.log('Script.js DOMContentLoaded - upload functionality handled by upload.js');
  
  // Load history on page load to ensure persistence across server restarts
  loadHistory();
  
  // Verify global functions are registered
  console.log('Checking global functions:');
  console.log('- window.switchTab:', typeof window.switchTab);
  console.log('- window.toggleMobileNav:', typeof window.toggleMobileNav);
  console.log('- window.closeMobileNav:', typeof window.closeMobileNav);
  console.log('- window.toggleStep:', typeof window.toggleStep);
  console.log('- window.toggleHistory:', typeof window.toggleHistory);
  
  // Only cleanup stray nodes, don't attach upload handlers
  try {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
    const toRemove = [];
    let node;
    while ((node = walker.nextNode())) {
      if (node.nodeValue && node.nodeValue.trim() === '2') toRemove.push(node);
    }
    toRemove.forEach(n => n.parentNode && n.parentNode.removeChild(n));
    if (toRemove.length) console.log(`Removed ${toRemove.length} stray '2' text node(s)`);
  } catch (e) {
    console.warn('Cleanup routine failed', e);
  }

  // Don't load history on page load - only when user switches to history tab
});



// --- Load Dropbox-Hosted NPY File ---
// --- Load NPY Directly from GitHub ---




// --- When user uploads manually, reset dropdown to 'None'
document.getElementById("fileInput").addEventListener("change", () => {
  document.getElementById("presetVolumeSelect").value = "none";
});



// --- Convert Google Drive link to direct ID ---
function extractDriveID(url) {
  // supports:
  // https://drive.google.com/file/d/FILEID/view?usp=sharing
  // https://drive.google.com/uc?id=FILEID&export=download
  // https://drive.google.com/open?id=FILEID

  const dMatch = url.match(/\/d\/([a-zA-Z0-9_-]+)/);
  if (dMatch) return dMatch[1];

  const idMatch = url.match(/id=([a-zA-Z0-9_-]+)/);
  if (idMatch) return idMatch[1];

  return null;
}

async function fetchFromGoogleDrive(fileId) {
  const base = "https://drive.google.com/uc?export=download&id=" + fileId;

  // First request (may return confirmation HTML)
  let resp = await fetch(base);
  let text = await resp.text();

  // If Google returned HTML, find confirm token
  if (text.includes("confirm=")) {
    const confirmToken = text.match(/confirm=([0-9A-Za-z_]+)/)[1];
    const downloadURL = base + "&confirm=" + confirmToken;

    resp = await fetch(downloadURL);
    return await resp.arrayBuffer();
  }

  // If the result is binary already
  if (resp.ok) {
    return await resp.arrayBuffer();
  }

  throw new Error("Google Drive fetch failed.");
}

async function loadCompressedVolume(npyUrl, metaUrl) {
  // Fetch compressed uint8 NPY
  const resp = await fetch(npyUrl);
  const arrayBuffer = await resp.arrayBuffer();
  const parsed = parseNpy(arrayBuffer);   // returns uint8 array

  // Fetch metadata
  const metaResp = await fetch(metaUrl);
  const meta = await metaResp.json();

  const { original_shape, min, max } = meta;

  // Convert uint8 → float32 in 0–1 range
  let vol = parsed.data;
  let volFloat = new Float32Array(vol.length);

  for (let i = 0; i < vol.length; i++) {
    volFloat[i] = vol[i] / 255;
  }

  // Restore original range
  for (let i = 0; i < volFloat.length; i++) {
    volFloat[i] = volFloat[i] * (max - min) + min;
  }

  // Reshape to 300x300xN
  const restored = {
    data: volFloat,
    shape: original_shape
  };

  return restored;
}

//new 
async function loadVolumeFromURL(url) {
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("Failed to fetch: " + resp.status);

    const arrayBuffer = await resp.arrayBuffer();

    const parsed = parseNpy(arrayBuffer);
    lastParsedVolume = parsed;

    renderImage(vtkImageFromNpy(parsed));
    document.getElementById("downloadNpy").disabled = false;

    console.log("Loaded volume:", url);

  } catch (err) {
    alert("Error loading volume:\n" + err.message);
  }
}

// ============ BACKEND INTEGRATION FOR MOTOR DETECTION ============

// Upload ZIP to backend and process
async function uploadAndProcessZip() {
  console.log('uploadAndProcessZip called');
  console.log('lastUploadedZip:', lastUploadedZip);
  if (!lastUploadedZip) {
    console.warn('No ZIP file selected');
    alert('Please select a ZIP file first');
    return;
  }

  const formData = new FormData();
  formData.append('zip_file', lastUploadedZip);

  try {
    // Show processing status
    updatePipelineStatus('preprocessing', 'running');
    
    const response = await fetch(`${backendUrl}/detect/`, {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    // Process streaming response
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.trim()) {
          try {
            const data = JSON.parse(line);
            handleBackendMessage(data);
          } catch (e) {
            console.error('Failed to parse line:', line, e);
          }
        }
      }
    }

    updatePipelineStatus('preprocessing', 'completed');
    updatePipelineStatus('detection', 'completed');
    updatePipelineStatus('clustering', 'completed');
    updatePipelineStatus('visualization', 'completed');

  } catch (error) {
    console.error('Upload error:', error);
    alert('Failed to process ZIP: ' + error.message);
    updatePipelineStatus('preprocessing', 'error');
  }
}

// Handle messages from backend
function handleBackendMessage(data) {
  if (data.stage === 'received') {
    console.log('Backend received file');
    updatePipelineStatus('preprocessing', 'running');
  }
  
  if (data.progress !== undefined) {
    console.log(`Progress: ${data.progress}%`);
    updatePipelineStatus('detection', 'running');
  }
  
  if (data.results) {
    console.log('Processing complete', data);
    
    // Update total motors
    if (data.total_motors !== undefined) {
      document.getElementById('totalMotorsValue').textContent = data.total_motors;
    }
    
    // Update elapsed time
    if (data.elapsed_ms) {
      const seconds = (data.elapsed_ms / 1000).toFixed(1);
      document.getElementById('avgProcTimeValue').textContent = `${seconds}s`;
    }
    
    // Display motor coordinates
    if (data.motors_coordinates) {
      displayMotorCoordinates(data.motors_coordinates);
    }
    
    // Auto-load volume if available
    if (data.transparent_volume_url) {
      currentTransparentVolumeUrl = backendUrl + data.transparent_volume_url;
      loadVolumeFromURL(currentTransparentVolumeUrl);
      
      // Show download button
      const downloadBtn = document.getElementById('downloadVolumeBtn');
      if (downloadBtn) downloadBtn.style.display = 'inline-block';
    }
  }
  
  if (data.error) {
    console.error('Backend error:', data.error);
    alert('Processing error: ' + data.error);
  }
}

// Display motor coordinates in the UI
function displayMotorCoordinates(motorsCoordinates) {
  const coordinatesWrap = document.getElementById('coordinatesWrap');
  const coordinatesDetails = document.getElementById('coordinatesDetails');
  
  if (!coordinatesWrap || !coordinatesDetails) return;
  
  coordinatesWrap.style.display = 'block';
  let coordsHtml = '';
  
  for (const [tomoId, motors] of Object.entries(motorsCoordinates)) {
    coordsHtml += `<strong style="color: #000000;">${tomoId}:</strong>\n`;
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
}

// Download transparent volume function
async function downloadTransparentVolume() {
  if (!currentTransparentVolumeUrl) {
    alert('No transparent volume available to download');
    return;
  }
  
  try {
    const response = await fetch(currentTransparentVolumeUrl);
    if (!response.ok) throw new Error('Failed to fetch volume');
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transparent_volume.npy';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    console.log('Transparent volume downloaded');
  } catch (error) {
    console.error('Download error:', error);
    alert('Failed to download volume: ' + error.message);
  }
}

// Update pipeline step status
function updatePipelineStatus(stepId, status) {
  // Map step IDs to their DOM elements
  const stepMap = {
    'preprocessing': 'step1',
    'detection': 'step2',
    'clustering': 'step3',
    'visualization': 'step4'
  };
  
  const domId = stepMap[stepId];
  if (!domId) return;
  
  // Find the step element and update its status
  const steps = document.querySelectorAll('.pipeline-step');
  steps.forEach(step => {
    const stepName = step.querySelector('.step-name')?.textContent?.toLowerCase();
    if (stepName && stepName.includes(stepId)) {
      const statusEl = step.querySelector('.step-status');
      if (statusEl) {
        if (status === 'running') {
          statusEl.textContent = 'Processing...';
          statusEl.style.color = '#ff9800';
        } else if (status === 'completed') {
          statusEl.textContent = 'Completed';
          statusEl.style.color = '#4caf50';
        } else if (status === 'error') {
          statusEl.textContent = 'Error';
          statusEl.style.color = '#f44336';
        }
      }
    }
  });
}

// Download transparent volume function
async function downloadTransparentVolume() {
  if (!currentTransparentVolumeUrl) {
    alert('No transparent volume available to download');
    return;
  }
  
  try {
    const response = await fetch(currentTransparentVolumeUrl);
    if (!response.ok) throw new Error('Failed to fetch volume');
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transparent_volume.npy';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
    
    console.log('Transparent volume downloaded');
  } catch (error) {
    console.error('Download error:', error);
    alert('Failed to download volume: ' + error.message);
  }
}

// Add upload button handler
document.addEventListener('DOMContentLoaded', () => {
  // Create an upload button if it doesn't exist
  const analysisSection = document.querySelector('#analysis .pipeline');
  if (analysisSection) {
    const uploadBtn = document.createElement('button');
    uploadBtn.textContent = 'Upload & Process ZIP';
    uploadBtn.style.cssText = 'margin-top: 20px; padding: 12px 24px; background-color: #016B61; color: white; border: none; cursor: pointer; font-size: 14px;';
    uploadBtn.onclick = uploadAndProcessZip;
    analysisSection.appendChild(uploadBtn);
  }
});
