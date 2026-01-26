# ============================================================================
# WEB PLATFORM INTEGRATION: VALIDATION CASE [tomo_2acf68_0135]
# ============================================================================

TARGET TOMOGRAM: tomo_2acf68
TARGET SLICE:    135
TOTAL SLICE: 300
GROUND TRUTH MOTOR: 1
OBJECTIVE:       Verify 'best.pt' model accuracy on the Web Platform.

------------------------------------------------------------------------------
1. EXPECTED COORDINATES (For Validation)
------------------------------------------------------------------------------
When the model runs on 'tomo_2acf68_0135.jpg', the output should match these
values.

[A] GROUND TRUTH (Gold Standard):
   • X: 468.0
   • Y: 225.0
   • Z: 135.0

[B] MODEL PREDICTION (From Validation Results):
   • X: ~468.0  (± 0.8 nm deviation)
   • Y: ~225.0  (± 0.8 nm deviation)
   • Z: 135.0
   • Status:    CORRECT DETECTION (True Positive)

------------------------------------------------------------------------------
2. PERFORMANCE METRICS
------------------------------------------------------------------------------
The web platform should display these confidence levels for this motor:

• Final Confidence Score:  0.44  (After DBSCAN Clustering)
• Raw Confidence Score:    0.39  (Before Clustering)
• Euclidean Error:         0.80 nm (High Accuracy)

------------------------------------------------------------------------------
3. INTEGRATION PARAMETERS (Must match Python Backend)
------------------------------------------------------------------------------
Ensure the 'FlagellarMotorDetector' class is initialized with these EXACT 
settings to reproduce the 0.8nm accuracy:

model = YOLO('best.pt')

# Hyperparameters
CONF_THRESHOLD     = 0.25   # Lower threshold to catch the motor
DBSCAN_EPS         = 50     # Clustering search radius
DBSCAN_MIN_SAMPLES = 3      # Min points to form a motor
MIN_CLUSTER_SIZE   = 3      # Filter small noise
MIN_DISTANCE       = 100    # Remove duplicates
