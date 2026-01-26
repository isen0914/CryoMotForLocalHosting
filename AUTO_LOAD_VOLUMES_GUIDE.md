# Auto-Load 3D Volumes Feature

## Overview

The system now automatically loads both NPY files (bacteria volume and motor locations) into the 3D viewer immediately after detection completes, eliminating the need for manual download and upload.

## How It Works

### 1. Backend Processing

When the backend completes processing, it generates two NPY files:

- **Processed Volume** (`*_processed_volume.npy`) - The cleaned 3D volume showing bacteria with background removed
- **Transparent Volume** (`*_transparent_volume.npy`) - Overlay showing motor locations as highlights

Both files are saved to the `/outputs` directory and their URLs are returned in the final JSON response:

```json
{
  "processed_volume_url": "/outputs/filename_processed_volume.npy",
  "transparent_volume_url": "/outputs/filename_transparent_volume.npy"
}
```

### 2. Frontend URL Storage

The frontend (`upload.js`) captures these URLs and stores them globally:

```javascript
window.processedVolumeUrl = BACKEND_URL + data.processed_volume_url;
window.transparentVolumeUrl = BACKEND_URL + data.transparent_volume_url;
window.volumesLoaded = false; // Flag to track if volumes have been auto-loaded
```

### 3. Automatic Tab Switching

After processing completes, the system automatically switches to the 3D Visualization tab:

```javascript
if (window.processedVolumeUrl || window.transparentVolumeUrl) {
  alert(
    "Processing complete! Switching to 3D Visualization and loading volumes..."
  );
  setTimeout(() => {
    if (typeof window.switchTab === "function") {
      window.switchTab("visualization");
    }
  }, 500);
}
```

### 4. Auto-Loading Mechanism

When the visualization tab is opened, the `switchTab` function in `script.js` checks for available volume URLs:

```javascript
if (tabName === "visualization") {
  if (
    (window.processedVolumeUrl || window.transparentVolumeUrl) &&
    !window.volumesLoaded
  ) {
    // Auto-load both volumes
  }
}
```

### 5. File Fetching and Loading

The `autoLoadFileIntoInput` function:

1. Fetches the NPY file from the URL
2. Converts it to a File object
3. Programmatically sets it on the file input element
4. Triggers the change event to load it into the 3D viewer

```javascript
window.autoLoadFileIntoInput(url, inputId, filename);
```

## User Experience

### Workflow:

1. **Upload** → User uploads ZIP file with tomogram images
2. **Process** → Backend runs YOLO detection and generates volumes
3. **Auto-Switch** → Frontend automatically switches to 3D Visualization tab
4. **Auto-Load** → Both NPY files are automatically loaded into the viewer
5. **View** → User can immediately see the 3D visualization

### Visual Feedback:

- **Orange notification**: "⏳ Loading volumes automatically..."
- **Green notification**: "✓ 2 volume(s) automatically loaded from detection results"
- **Yellow notification**: "⚠ 1/2 volume(s) loaded (1 failed)" (if partial failure)
- **Red notification**: "✗ Failed to load volumes automatically" (if complete failure)

## Benefits

✅ **No Manual Downloads** - NPY files don't need to be downloaded to disk
✅ **No Manual Uploads** - No need to browse and select files
✅ **Instant Visualization** - Seamless transition from detection to 3D viewing
✅ **Better UX** - Reduces steps from ~5 actions to 1
✅ **Automatic** - Works without user intervention

## Technical Details

### File Input Elements:

- `fileInput` - Loads the processed bacteria volume
- `motorsFile` - Loads the transparent motor locations volume

### Key Functions:

- `handleBackendResponse()` - Captures volume URLs from backend response
- `switchTab()` - Detects visualization tab and triggers auto-load
- `autoLoadFileIntoInput()` - Fetches and loads NPY files programmatically

### Error Handling:

- Network errors during fetch
- Missing input elements
- Failed file conversions
- Proper promise rejection for caller handling

## Files Modified

1. **frontend/upload.js**

   - Enhanced URL storage with logging
   - Added automatic tab switching after processing
   - Improved `autoLoadFileIntoInput` with better error handling

2. **frontend/script.js**
   - Enhanced auto-loading with error tracking
   - Added detailed logging for debugging
   - Improved notification messages with counts

## Testing

To test the auto-load feature:

1. Start backend: `cd backend && python main.py`
2. Open frontend in browser
3. Upload a ZIP file with tomogram images
4. Wait for processing to complete
5. Observe automatic tab switch
6. Verify both volumes load into the 3D viewer
7. Check browser console for detailed logs

## Debugging

If auto-load doesn't work, check:

- Browser console for error messages
- Network tab to verify NPY files are served correctly
- Verify `window.processedVolumeUrl` and `window.transparentVolumeUrl` are set
- Confirm file input elements exist: `fileInput` and `motorsFile`
- Check if `window.autoLoadFileIntoInput` function is defined

## Future Enhancements

Possible improvements:

- Add progress indicators during file fetching
- Implement retry logic for failed fetches
- Add option to disable auto-loading
- Cache volumes for quicker re-loading
- Support for multiple tomogram results
