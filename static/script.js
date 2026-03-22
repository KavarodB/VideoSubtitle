// --- DOM Element Initialization ---
function getElement(id) {
  // ... (existing getElement function)
  const element = document.getElementById(id);
  if (!element) {
    console.warn(`Element with ID "${id}" not found.`);
  }
  return element;
}

const DOM = {
  // Upload/Main View Elements
  uploadForm: getElement("uploadForm"),
  uploadFileForm: getElement("uploadFileForm"), // CRITICAL: This element is used for the submit listener
  uploadArea: getElement("uploadArea"),
  fileInput: getElement("fileInput"),
  fileName: getElement("fileName"),
  uploadBtn: getElement("uploadBtn"),
  clearBtn: getElement("clearBtn"),
  resultSection: getElement("resultSection"),
  transcript: getElement("transcript"),
  segmentsContainer: getElement("segments"),
  videoWrap: getElement("videoWrap"),
  saveBtn: getElement("saveBtn"),
  assLink: getElement("assLink"),

  // Status Elements (Shared)
  status: getElement("status"), // Used for upload status
  statusBox: getElement("statusBox"),
};

// --- State Management ---
const API_URL = "";
let selectedFile = null;
let currentFileId = null;
let segmentsData = [];
let isEditing = false;

// Customization Settings
let customization = {
  font: "Arial",
  fontSize: 24,
  position: "bottom", // top, middle, bottom
  cadence: "instant", // instant, fade-in, pop, slide-up, slide-down, typewriter
  duration: 2,
  animationSpeed: 1,
  color: "#ffffff",
  augmentation: false,
};

// --- Utility & Display Functions ---

/**
 * Displays a status message to the user, using the appropriate container.
 * @param {string} message The HTML message to display.
 * @param {'loading'|'success'|'error'} type The type of status.
 * @param {boolean} useStatusBox Whether to use the smaller statusBox (for editor actions) or the main status (for upload).
 */
function showStatus(message, type, useStatusBox = false) {
  const el = useStatusBox ? DOM.statusBox : DOM.status;
  if (!el) return;

  el.innerHTML = message;
  el.className = `status show ${type}`;

  // Clear the *other* status box if showing
  const otherEl = useStatusBox ? DOM.status : DOM.statusBox;
  if (otherEl) otherEl.classList.remove("show");
}

/**
 * Updates the displayed file name.
 */
function updateFileName() {
  DOM.fileName.textContent = selectedFile
    ? `Selected: ${selectedFile.name}`
    : "";
}

/**
 * Safely escapes HTML content for display in text areas.
 * @param {string} text The text to escape.
 * @returns {string} The escaped HTML string.
 */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Creates or updates a video player element.
 * @param {string} id The ID of the video element.
 * @param {string} src The source URL for the video.
 * @returns {HTMLVideoElement} The video element.
 */
function createOrUpdateVideoPlayer(id, src) {
  let player = getElement(id);
  if (!player) {
    player = document.createElement("video");
    player.id = id;
    player.controls = true;
    player.style.maxHeight = "480px";
    player.style.width = "100%";
    player.style.marginTop = "12px";

    // Insert Original video before any existing content in videoWrap
    if (id === "videoPreview" && DOM.videoWrap.firstChild) {
      DOM.videoWrap.insertBefore(player, DOM.videoWrap.firstChild);
    } else {
      DOM.videoWrap.appendChild(player);
    }
  }
  player.src = src;
  return player;
}

// --- Editor Logic ---

/**
 * Renders the segment data into the segments container, based on the current editing state.
 */
function renderSegments() {
  DOM.segmentsContainer.innerHTML = "";

  segmentsData.forEach((s, i) => {
    const wrap = document.createElement("div");
    wrap.className = "segment";

    const times = document.createElement("div");
    times.className = "seg-times";

    const textWrap = document.createElement("div");
    textWrap.className = "seg-text";

    if (isEditing) {
      // Editable mode (from the second HTML)
      times.innerHTML = `Start: <input class="edit-start" value="${
        s.start != null ? s.start : ""
      }" style="width:80px" /> <br/> End: <input class="edit-end" value="${
        s.end != null ? s.end : ""
      }" style="width:80px" />`;
      const ta = document.createElement("textarea");
      ta.className = "edit-text";
      ta.value = s.text || "";
      textWrap.appendChild(ta);
    } else {
      // Read-only mode (from the second HTML)
      times.innerHTML =
        (s.start != null ? s.start : "—") +
        " — " +
        (s.end != null ? s.end : "—");
      const p = document.createElement("div");
      p.textContent = s.text || "";
      textWrap.appendChild(p);
    }

    wrap.appendChild(times);
    wrap.appendChild(textWrap);
    DOM.segmentsContainer.appendChild(wrap);
  });
}

/**
 * Collects the segment data from the editable inputs.
 * @returns {Array<object>} The collected segments.
 */
function collectEditedSegments() {
  const segNodes = DOM.segmentsContainer.querySelectorAll(".segment");
  return Array.from(segNodes).map((node) => {
    const startValue = node.querySelector(".edit-start").value;
    const endValue = node.querySelector(".edit-end").value;
    const text = node.querySelector(".edit-text").value;

    return {
      start: startValue === "" ? null : parseFloat(startValue),
      end: endValue === "" ? null : parseFloat(endValue),
      text: text,
    };
  });
}

// --- API Call Handlers ---

/**
 * Displays transcription results and switches to the result view.
 * @param {object} data The transcription result data.
 */
function displayResults(data) {
  const { transcript, segments, file_id, json, srt, ass } = data;

  currentFileId = file_id;
  segmentsData = segments || [];
  DOM.transcript.textContent = transcript;

  // Set links
  if (DOM.assLink) DOM.assLink.href = ass ? `/${ass.replace(/^\//, "")}` : "#";

  // Show original video preview
  createOrUpdateVideoPlayer("videoPreview", `/tmp/${file_id}.mp4`);

  // Set view mode and render (read-only — editing disabled in frontend)
  isEditing = false;
  if (DOM.saveBtn) DOM.saveBtn.style.display = "block";
  renderSegments();

  // Switch views
  if (DOM.uploadForm) DOM.uploadForm.style.display = "none";
  if (DOM.resultSection) DOM.resultSection.style.display = "block";
}

/**
 * Loads a transcript from the server using a file ID (used when loading via URL or canceling edit).
 * @param {string} fileId The ID of the file.
 * @param {boolean} initialLoad True if loading from URL on page load.
 */
async function loadTranscript(fileId, initialLoad = true) {
  if (initialLoad) {
    DOM.uploadForm.style.display = "none";
    showStatus("Loading transcript...", "loading", true);
    DOM.resultSection.style.display = "block";
  }

  try {
    const res = await fetch(`/tmp/${fileId}.json`);
    if (!res.ok) {
      showStatus("Transcript not found.", "error", true);
      DOM.resultSection.style.display = "none";
      DOM.uploadForm.style.display = "block";
      return;
    }

    const data = await res.json();

    // If initial load or cancel, use data from server
    if (initialLoad || !isEditing) {
      displayResults({ ...data, file_id: fileId });
      showStatus("Transcript loaded successfully.", "success", true);
    }
  } catch (err) {
    showStatus("Error loading transcript: " + err.message, "error", true);
    DOM.resultSection.style.display = "none";
    DOM.uploadForm.style.display = "block";
  }
}

/**
 * Handles the file upload and transcription API call.
 */
async function handleUpload() {
  if (!selectedFile) {
    showStatus("Please select a file first", "error");
    return;
  }

  DOM.uploadBtn.disabled = true;
  showStatus('<span class="spinner"></span>Transcribing...', "loading");

  const formData = new FormData();
  formData.append("file", selectedFile);

  try {
    // 1. Fetch Request
    const response = await fetch(`${API_URL}/transcribe`, {
      method: "POST",
      body: formData,
    });

    // 2. SUCCESS PATH (Status 2xx)
    if (response.ok) {
      // CRITICAL: Consume the response body immediately and fully
      const data = await response.json();

      displayResults(data);
      showStatus("✓ Transcription complete!", "success", true);
    } else {
      // 3. ERROR PATH (Status 4xx/5xx)
      let errMsg = `Transcription failed (Status: ${response.status})`;

      try {
        const responseText = await response.text();

        if (responseText) {
          errMsg = responseText;
          try {
            const errJson = JSON.parse(responseText);
            if (errJson && errJson.detail) {
              errMsg = errJson.detail;
            } else if (typeof errJson === "object" && errJson !== null) {
              errMsg = `Server Error: ${JSON.stringify(errJson)}`;
            }
          } catch (jsonErr) {
            // responseText is used as errMsg
          }
        }
      } catch (readBodyErr) {
        // original errMsg is used
      }

      throw new Error(errMsg);
    }
  } catch (error) {
    // 4. Network/Error Catch
    const msg = error && error.message ? error.message : String(error);
    showStatus(`Error: ${msg}`, "error");
    DOM.uploadForm.style.display = "block";
    DOM.resultSection.style.display = "none";
  } finally {
    // 5. Cleanup (Guaranteed to run)
    DOM.uploadBtn.disabled = false;
  }
}

/**
 * Handles collecting segments and triggering the subtitle burn API.
 */
async function handleBurn() {
  if (!currentFileId) {
    return showStatus("Missing file ID.", "error", true);
  }

  // Collect segments based on current state
  // Editing disabled in frontend — always send server-side segmentsData
  const payloadSegments = segmentsData;

  showStatus(
    '<span class="spinner"></span>Burning subtitles...',
    "loading",
    true,
  );

  try {
    const resp = await fetch(`${API_URL}/burn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_id: currentFileId,
        segments: payloadSegments,
        customization: customization,
      }),
    });

    if (!resp.ok) {
      let errMsg = "Burn failed";
      try {
        const errJson = await resp.json();
        if (errJson) {
          if (errJson.detail) errMsg = errJson.detail;
          else if (errJson.error) errMsg = errJson.error;
          else if (typeof errJson === "string") errMsg = errJson;
        }
      } catch (readJsonErr) {
        try {
          const txt = await resp.text();
          if (txt) errMsg = txt;
        } catch (readTextErr) {
          // ignore
        }
      }
      throw new Error(errMsg);
    }

    const body = await resp.json();

    // Cache-bust so the browser always fetches the freshly burned file
    const burnedUrl = body.burned + "?t=" + Date.now();

    // Find the player regardless of whether a previous burn renamed it
    const existingPlayer =
      getElement("burnedPreview") || getElement("videoPreview");
    if (existingPlayer) {
      existingPlayer.id = "burnedPreview";
      existingPlayer.src = burnedUrl;
      existingPlayer.load();
    } else {
      createOrUpdateVideoPlayer("burnedPreview", burnedUrl);
    }

    showStatus(
      "✓ Burn complete! Download available in the preview player.",
      "success",
      true,
    );
  } catch (e) {
    showStatus(`Error: ${e.message}`, "error", true);
  }
}

/**
 * Updates the live preview based on current customization settings.
 */
function updatePreview() {
  const preview = document.getElementById("previewSubtitle");
  if (!preview) return;

  // Update font
  preview.style.fontFamily = customization.font;

  // Update font size
  preview.style.fontSize = customization.fontSize + "px";

  // Update color
  preview.style.color = customization.color;

  // Update position
  const preview_box = document.getElementById("livePreview");
  if (preview_box) {
    preview_box.style.justifyContent =
      customization.position === "top"
        ? "flex-start"
        : customization.position === "middle"
          ? "center"
          : "flex-end";
  }

  // Update animation
  preview.className = `subtitle-preview ${customization.cadence}`;

  // Apply animation speed (via CSS variable or direct modification)
  preview.style.animationDuration = 1 / customization.animationSpeed + "s";
}

/**
 * Clears the selected file, resets the UI, and returns to the upload view.
 */
function clearState() {
  selectedFile = null;
  currentFileId = null;
  segmentsData = [];
  isEditing = false;

  // Reset file input and display
  DOM.fileInput.value = "";
  DOM.fileName.textContent = "";

  // Clear and hide status messages
  if (DOM.status) DOM.status.classList.remove("show");
  if (DOM.statusBox) DOM.statusBox.classList.remove("show");

  // Remove dynamically added video elements (optional for full reset)
  const preview = getElement("videoPreview");
  if (preview) preview.remove();
  const burned = getElement("burnedPreview");
  if (burned) burned.remove();

  // Switch views
  DOM.resultSection.style.display = "none";
  DOM.uploadForm.style.display = "block";
}

// --- Event Listener Registration ---

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const fileId = params.get("file_id");

  if (fileId) {
    // If we're on a page without the editor DOM, redirect to the editor page
    if (DOM.resultSection) {
      loadTranscript(fileId);
    } else {
      window.location.href = `/static/editor.html?file_id=${encodeURIComponent(
        fileId,
      )}`;
    }
  } else {
    if (DOM.resultSection) DOM.resultSection.style.display = "none";
    if (DOM.uploadForm) DOM.uploadForm.style.display = "block";
  }

  // --- Upload/File Selection Listeners ---
  if (DOM.uploadArea && DOM.fileInput) {
    DOM.uploadArea.addEventListener("click", () => DOM.fileInput.click());

    DOM.uploadArea.addEventListener("dragover", (e) => {
      e.preventDefault();
      DOM.uploadArea.classList.add("dragover");
    });

    DOM.uploadArea.addEventListener("dragleave", () => {
      DOM.uploadArea.classList.remove("dragover");
    });

    DOM.uploadArea.addEventListener("drop", (e) => {
      e.preventDefault();
      DOM.uploadArea.classList.remove("dragover");
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        selectedFile = files[0];
        updateFileName();
      }
    });

    DOM.fileInput.addEventListener("change", (e) => {
      if (e.target.files.length > 0) {
        selectedFile = e.target.files[0];
        updateFileName();
      }
    });
  }

  // --- Customization Controls ---
  try {
    // Font Selection
    const fontSelect = document.getElementById("fontSelect");
    if (fontSelect) {
      fontSelect.addEventListener("change", (e) => {
        customization.font = e.target.value;
        updatePreview();
      });
    }

    // Font Size Slider
    const fontSizeSlider = document.getElementById("fontSizeSlider");
    const fontSizeValue = document.getElementById("fontSizeValue");
    if (fontSizeSlider && fontSizeValue) {
      fontSizeSlider.addEventListener("input", (e) => {
        customization.fontSize = parseInt(e.target.value);
        fontSizeValue.textContent = customization.fontSize;
        updatePreview();
      });
    }

    // Color Picker
    const colorPicker = document.getElementById("colorPicker");
    const colorValue = document.getElementById("colorValue");
    if (colorPicker && colorValue) {
      colorPicker.addEventListener("input", (e) => {
        customization.color = e.target.value;
        colorValue.textContent = customization.color.toUpperCase();
        updatePreview();
      });
    }

    // Position Buttons
    const positionButtons = document.querySelectorAll(".position-btn-compact");
    if (positionButtons && positionButtons.length) {
      positionButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
          const position = btn.dataset.position;
          customization.position = position;
          // Update active state
          positionButtons.forEach((b) =>
            b.classList.toggle("active", b.dataset.position === position),
          );
          updatePreview();
        });
      });
      // Set bottom as default active
      positionButtons.forEach((btn) => {
        if (btn.dataset.position === "bottom") btn.classList.add("active");
      });
    }

    // Cadence/Animation Select
    const cadenceSelect = document.getElementById("cadenceSelect");
    if (cadenceSelect) {
      cadenceSelect.addEventListener("change", (e) => {
        customization.cadence = e.target.value;
        updatePreview();
      });
    }

    // Duration Slider
    const durationSlider = document.getElementById("durationSlider");
    const durationValue = document.getElementById("durationValue");
    if (durationSlider && durationValue) {
      durationSlider.addEventListener("input", (e) => {
        customization.duration = parseFloat(e.target.value);
        durationValue.textContent = customization.duration;
        updatePreview();
      });
    }

    // Animation Speed Slider
    const speedSlider = document.getElementById("speedSlider");
    const speedValue = document.getElementById("speedValue");
    if (speedSlider && speedValue) {
      speedSlider.addEventListener("input", (e) => {
        customization.animationSpeed = parseFloat(e.target.value);
        speedValue.textContent = customization.animationSpeed.toFixed(1);
        updatePreview();
      });
    }

    // Augmentation Checkbox
    const augmentationCheckbox = document.getElementById(
      "augmentationCheckbox",
    );
    if (augmentationCheckbox) {
      augmentationCheckbox.addEventListener("change", (e) => {
        customization.augmentation = e.target.checked;
        updatePreview();
      });
    }

    // Initialize preview
    updatePreview();
  } catch (e) {
    console.warn("Error setting up customization controls:", e);
  }

  if (DOM.uploadBtn) {
    DOM.uploadBtn.addEventListener("click", (e) => {
      if (e && typeof e.preventDefault === "function") e.preventDefault();
      handleUpload();
    });
  }
  if (DOM.clearBtn) DOM.clearBtn.addEventListener("click", clearState);
  if (DOM.saveBtn) DOM.saveBtn.addEventListener("click", handleBurn);
});
