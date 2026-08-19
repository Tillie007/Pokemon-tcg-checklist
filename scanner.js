(function () {
  'use strict';

  const Match = window.PokemonScannerMatch;
  if (!Match) {
    console.error('Kaartscanner kon de vergelijkingsmodule niet laden.');
    return;
  }

  const CARD_ASPECT = 63 / 88;
  const ANALYSIS_INTERVAL_MS = 140;
  const AUTO_CAPTURE_SCORE = 1;
  const SCANNER_VERSION = '2.1.0';
  const TESSERACT_URL = 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
  const IMAGE_FETCH_TIMEOUT_MS = 2400;
  const visualFingerprintCache = new Map();

  const state = {
    open: false,
    stream: null,
    timer: 0,
    operation: 0,
    cameraStartedAt: 0,
    stability: 0,
    previousLuma: null,
    previousMean: 0,
    motionBaseline: 2.5,
    capturing: false,
    processing: false,
    captureCanvas: null,
    captureUrl: '',
    evidence: null,
    ranked: [],
    selectedKey: '',
    variant: 'Normal',
    quantity: 1,
    batchCount: 0,
    batchItems: [],
    ocrWorker: null,
    ocrWarmPromise: null,
    toastTimer: 0
  };

  let ui = {};

  function appCards() {
    try {
      if (typeof cards !== 'undefined' && Array.isArray(cards)) return cards;
    } catch (_) {}
    if (window.DATA && Array.isArray(window.DATA.cards)) return window.DATA.cards;
    return [];
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[character]));
  }

  function scannerIcon() {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M8 8h8v8H8z"/></svg>';
  }

  function buildScanner() {
    const section = document.createElement('section');
    section.id = 'pokemonScanner';
    section.className = 'tcg-scanner';
    section.hidden = true;
    section.setAttribute('aria-label', 'Pokémon kaartscanner');
    section.innerHTML = `
      <header class="scanner-topbar">
        <div class="scanner-title-wrap">
          <span class="scanner-kicker">Automatische herkenning</span>
          <h2>Kaartscanner</h2>
        </div>
        <div class="scanner-top-actions">
          <button type="button" id="scannerBatchTop" class="scanner-icon-button scanner-batch-button" aria-label="Toegevoegde kaarten bekijken" hidden>
            <svg viewBox="0 0 24 24"><path d="M5 7h10M5 12h10M5 17h7M18 14v6M15 17h6"/></svg>
            <span id="scannerBatchBadge" class="scanner-batch-badge">0</span>
          </button>
          <button type="button" id="scannerRetryTop" class="scanner-icon-button" aria-label="Opnieuw scannen" hidden>
            <svg viewBox="0 0 24 24"><path d="M4 4v6h6M20 20v-6h-6M5.4 15a7 7 0 0 0 11.8 2.2L20 14M4 10l2.8-3.2A7 7 0 0 1 18.6 9"/></svg>
          </button>
          <button type="button" id="scannerClose" class="scanner-icon-button" aria-label="Scanner sluiten">
            <svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>
          </button>
        </div>
      </header>
      <main class="scanner-main">
        <section id="scannerCameraScreen" class="scanner-screen">
          <div class="scanner-camera-layout">
            <div id="scannerCameraShell" class="scanner-camera-shell">
              <video id="scannerVideo" class="scanner-video" playsinline muted></video>
              <div id="scannerCardGuide" class="scanner-card-guide" data-quality="bad">
                <i class="scanner-corner tl"></i><i class="scanner-corner tr"></i>
                <i class="scanner-corner bl"></i><i class="scanner-corner br"></i>
                <div class="scanner-countdown" aria-hidden="true">
                  <svg viewBox="0 0 56 56"><circle class="scanner-countdown-track" cx="28" cy="28" r="24"></circle><circle class="scanner-countdown-value" cx="28" cy="28" r="24"></circle></svg>
                  <span class="scanner-countdown-icon"><svg viewBox="0 0 24 24"><path d="M8 7 9.5 5h5L16 7h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zM12 10a3 3 0 1 0 0 6 3 3 0 0 0 0-6"/></svg></span>
                </div>
              </div>
              <div id="scannerCameraHint" class="scanner-camera-hint" data-quality="bad">
                <span class="scanner-quality-dot"></span><span id="scannerHintText">Camera wordt gestart…</span>
              </div>
            </div>
            <canvas id="scannerAnalysisCanvas" width="96" height="134" hidden></canvas>
            <div id="scannerQualityPanel" class="scanner-quality-panel" style="--scanner-progress:0">
              <div class="scanner-quality-head"><b id="scannerQualityTitle">Leg de kaart in het kader</b><span class="scanner-auto-label">Autoscan aan</span></div>
              <div class="scanner-progress-track"><div class="scanner-progress-fill"></div></div>
              <div class="scanner-quality-metrics">
                <span class="scanner-metric">Licht<b id="scannerLightMetric">—</b></span>
                <span class="scanner-metric">Scherpte<b id="scannerSharpMetric">—</b></span>
                <span class="scanner-metric">Beweging<b id="scannerMotionMetric">—</b></span>
              </div>
            </div>
            <div class="scanner-camera-actions">
              <button type="button" id="scannerManualCapture" class="scanner-action-button primary">Nu foto nemen</button>
              <button type="button" id="scannerChoosePhoto" class="scanner-action-button">Kies foto</button>
              <input id="scannerFileInput" type="file" accept="image/*" hidden>
            </div>
            <p class="scanner-footnote">De scanner wacht tot de kaart scherp en rustig ligt. Kleine bewegingen van je hand worden bewust genegeerd.</p>
          </div>
        </section>

        <section id="scannerProcessingScreen" class="scanner-screen" hidden>
          <div class="scanner-processing-wrap">
            <img id="scannerProcessingImage" class="scanner-captured-preview" alt="Gescande kaart">
            <div class="scanner-spinner" aria-hidden="true"></div>
            <h3 id="scannerProcessingTitle">Kaart wordt gelezen…</h3>
            <p id="scannerProcessingText">Naam, kaartnummer en afbeelding worden met elkaar vergeleken.</p>
            <div class="scanner-process-progress"><span id="scannerProcessFill" style="--process-progress:8%"></span></div>
          </div>
        </section>

        <section id="scannerResultsScreen" class="scanner-screen" hidden>
          <div class="scanner-results-wrap">
            <div class="scanner-result-summary">
              <img id="scannerResultImage" alt="Gescande kaart">
              <div>
                <h3 id="scannerResultTitle">Resultaat</h3>
                <p id="scannerResultText"></p>
                <span id="scannerConfidence" class="scanner-confidence-pill low">Nog onvoldoende zekerheid</span>
              </div>
            </div>
            <div class="scanner-refine">
              <input id="scannerRefineInput" type="search" placeholder="Verfijn op naam, set of kaartnummer" autocomplete="off">
              <button type="button" id="scannerRefineButton">Zoek</button>
            </div>
            <div id="scannerCandidateList" class="scanner-candidate-list"></div>
            <section id="scannerSelection" class="scanner-selection" hidden>
              <div class="scanner-selection-head">
                <img id="scannerSelectedImage" alt="Geselecteerde kaart">
                <div><span class="scanner-selection-kicker">Geselecteerd</span><h3 id="scannerSelectedName"></h3><p id="scannerSelectedMeta"></p></div>
              </div>
              <span class="scanner-field-label">Uitvoering</span>
              <div class="scanner-variant-row">
                <button type="button" class="scanner-variant-button active" data-scanner-variant="Normal">Normaal</button>
                <button type="button" class="scanner-variant-button" data-scanner-variant="Reverse Holo">Reverse</button>
                <button type="button" class="scanner-variant-button" data-scanner-variant="Holo">Holo</button>
              </div>
              <span class="scanner-field-label">Aantal toevoegen</span>
              <div class="scanner-quantity-row"><button type="button" id="scannerQtyMinus" aria-label="Aantal verlagen">−</button><b id="scannerQtyValue">1</b><button type="button" id="scannerQtyPlus" aria-label="Aantal verhogen">+</button></div>
              <button type="button" id="scannerSaveCard" class="scanner-save-button">Toevoegen aan mijn collectie</button>
            </section>
            <div class="scanner-results-actions">
              <button type="button" id="scannerScanAgain" class="primary">Opnieuw scannen</button>
              <button type="button" id="scannerFinish">Klaar</button>
            </div>
          </div>
        </section>

        <section id="scannerBatchScreen" class="scanner-screen" hidden>
          <div class="scanner-batch-summary">
            <div class="scanner-batch-check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m6 12 4 4 8-9"/></svg></div>
            <div id="scannerBatchCards" class="scanner-batch-cards" aria-hidden="true"></div>
            <h3 id="scannerBatchTitle">Kaarten toegevoegd</h3>
            <p id="scannerBatchText">Je kaarten staan veilig in je collectie.</p>
            <div class="scanner-batch-actions">
              <button type="button" id="scannerBatchContinue">${scannerIcon()}<span>Scan verder</span></button>
              <button type="button" id="scannerBatchCollection" class="primary"><span>Bekijk collectie</span><b>›</b></button>
            </div>
          </div>
        </section>
      </main>
      <div id="scannerToast" class="scanner-toast" role="status" aria-live="polite"></div>`;
    document.body.appendChild(section);

    ui = {
      root: section,
      cameraScreen: document.getElementById('scannerCameraScreen'),
      processingScreen: document.getElementById('scannerProcessingScreen'),
      resultsScreen: document.getElementById('scannerResultsScreen'),
      batchScreen: document.getElementById('scannerBatchScreen'),
      video: document.getElementById('scannerVideo'),
      shell: document.getElementById('scannerCameraShell'),
      guide: document.getElementById('scannerCardGuide'),
      hint: document.getElementById('scannerCameraHint'),
      hintText: document.getElementById('scannerHintText'),
      qualityPanel: document.getElementById('scannerQualityPanel'),
      qualityTitle: document.getElementById('scannerQualityTitle'),
      lightMetric: document.getElementById('scannerLightMetric'),
      sharpMetric: document.getElementById('scannerSharpMetric'),
      motionMetric: document.getElementById('scannerMotionMetric'),
      analysisCanvas: document.getElementById('scannerAnalysisCanvas'),
      manualCapture: document.getElementById('scannerManualCapture'),
      fileInput: document.getElementById('scannerFileInput'),
      batchTop: document.getElementById('scannerBatchTop'),
      batchBadge: document.getElementById('scannerBatchBadge'),
      retryTop: document.getElementById('scannerRetryTop'),
      processingImage: document.getElementById('scannerProcessingImage'),
      processingTitle: document.getElementById('scannerProcessingTitle'),
      processingText: document.getElementById('scannerProcessingText'),
      processFill: document.getElementById('scannerProcessFill'),
      resultImage: document.getElementById('scannerResultImage'),
      resultTitle: document.getElementById('scannerResultTitle'),
      resultText: document.getElementById('scannerResultText'),
      confidence: document.getElementById('scannerConfidence'),
      refineInput: document.getElementById('scannerRefineInput'),
      candidateList: document.getElementById('scannerCandidateList'),
      selection: document.getElementById('scannerSelection'),
      selectedImage: document.getElementById('scannerSelectedImage'),
      selectedName: document.getElementById('scannerSelectedName'),
      selectedMeta: document.getElementById('scannerSelectedMeta'),
      qtyValue: document.getElementById('scannerQtyValue'),
      batchCards: document.getElementById('scannerBatchCards'),
      batchTitle: document.getElementById('scannerBatchTitle'),
      batchText: document.getElementById('scannerBatchText'),
      toast: document.getElementById('scannerToast')
    };

    document.getElementById('scannerClose').addEventListener('click', closeScanner);
    ui.batchTop.addEventListener('click', showBatchSummary);
    ui.retryTop.addEventListener('click', resetToCamera);
    ui.manualCapture.addEventListener('click', () => captureFromCamera(false));
    document.getElementById('scannerChoosePhoto').addEventListener('click', () => ui.fileInput.click());
    ui.fileInput.addEventListener('change', onPhotoChosen);
    document.getElementById('scannerRefineButton').addEventListener('click', refineCandidates);
    ui.refineInput.addEventListener('keydown', event => { if (event.key === 'Enter') refineCandidates(); });
    document.getElementById('scannerScanAgain').addEventListener('click', resetToCamera);
    document.getElementById('scannerFinish').addEventListener('click', closeScanner);
    document.getElementById('scannerBatchContinue').addEventListener('click', resetToCamera);
    document.getElementById('scannerBatchCollection').addEventListener('click', openCollectionFromScanner);
    document.getElementById('scannerQtyMinus').addEventListener('click', () => setQuantity(state.quantity - 1));
    document.getElementById('scannerQtyPlus').addEventListener('click', () => setQuantity(state.quantity + 1));
    document.getElementById('scannerSaveCard').addEventListener('click', saveSelectedCard);
    section.querySelectorAll('[data-scanner-variant]').forEach(button => {
      button.addEventListener('click', () => setVariant(button.dataset.scannerVariant));
    });
    ui.candidateList.addEventListener('click', event => {
      const button = event.target.closest('[data-scanner-card-key]');
      if (button) selectCandidate(button.dataset.scannerCardKey);
    });

    window.addEventListener('pagehide', stopCamera);
  }

  function addLaunchers() {
    const statusActions = document.querySelector('.statusline .button-row');
    if (statusActions && !document.getElementById('openScannerDesktop')) {
      const button = document.createElement('button');
      button.type = 'button';
      button.id = 'openScannerDesktop';
      button.className = 'scanner-launch-button';
      button.innerHTML = `${scannerIcon()} Scan kaart`;
      button.addEventListener('click', openScanner);
      statusActions.prepend(button);
    }

    const bottomNav = document.querySelector('.bottom-nav');
    if (bottomNav && !document.getElementById('openScannerMobile')) {
      const button = document.createElement('button');
      button.type = 'button';
      button.id = 'openScannerMobile';
      button.className = 'bottom-nav-item scanner-nav-button';
      button.innerHTML = `${scannerIcon()}<span>Scanner</span>`;
      button.addEventListener('click', openScanner);
      const collectionButton = bottomNav.querySelector('[data-nav-target="collection"]');
      bottomNav.insertBefore(button, collectionButton || null);
    }
  }

  function showScreen(name) {
    ui.cameraScreen.hidden = name !== 'camera';
    ui.processingScreen.hidden = name !== 'processing';
    ui.resultsScreen.hidden = name !== 'results';
    ui.batchScreen.hidden = name !== 'batch';
    ui.retryTop.hidden = name === 'camera' || name === 'batch';
  }

  async function openScanner() {
    if (!ui.root) return;
    state.open = true;
    state.operation += 1;
    state.quantity = 1;
    state.variant = 'Normal';
    state.batchCount = 0;
    state.batchItems = [];
    ui.root.hidden = false;
    document.body.classList.add('scanner-is-open');
    updateBatchAction();
    showScreen('camera');
    warmOcrWorker();
    await startCamera();
  }

  function closeScanner() {
    state.open = false;
    state.operation += 1;
    state.processing = false;
    state.capturing = false;
    clearTimeout(state.timer);
    stopCamera();
    if (ui.root) ui.root.hidden = true;
    document.body.classList.remove('scanner-is-open');
  }

  async function resetToCamera() {
    state.operation += 1;
    state.processing = false;
    state.capturing = false;
    state.stability = 0;
    state.previousLuma = null;
    state.selectedKey = '';
    state.ranked = [];
    state.evidence = null;
    state.quantity = 1;
    state.variant = 'Normal';
    ui.refineInput.value = '';
    showScreen('camera');
    updateProgress(0);
    await startCamera();
  }

  async function startCamera() {
    stopCamera();
    if (!state.open || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setCameraMessage('Camera niet beschikbaar — kies een bestaande foto', 'bad');
      ui.manualCapture.disabled = true;
      return;
    }
    setCameraMessage('Camera wordt gestart…', 'warn');
    ui.manualCapture.disabled = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          frameRate: { ideal: 30, max: 60 }
        }
      });
      if (!state.open) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      state.stream = stream;
      ui.video.srcObject = stream;
      await ui.video.play();
      await enableContinuousCamera(stream.getVideoTracks()[0]);
      state.cameraStartedAt = performance.now();
      state.stability = 0;
      state.previousLuma = null;
      state.motionBaseline = 2.5;
      ui.manualCapture.disabled = false;
      setCameraMessage('Leg de volledige kaart binnen het kader', 'warn');
      scheduleAnalysis();
    } catch (error) {
      console.warn('Camera openen mislukt:', error);
      setCameraMessage('Geef cameratoegang of kies een foto', 'bad');
      ui.qualityTitle.textContent = 'Camera kon niet worden geopend';
      ui.manualCapture.disabled = true;
    }
  }

  async function enableContinuousCamera(track) {
    if (!track || typeof track.getCapabilities !== 'function' || typeof track.applyConstraints !== 'function') return;
    try {
      const capabilities = track.getCapabilities();
      const advanced = {};
      if (Array.isArray(capabilities.focusMode) && capabilities.focusMode.includes('continuous')) advanced.focusMode = 'continuous';
      if (Array.isArray(capabilities.exposureMode) && capabilities.exposureMode.includes('continuous')) advanced.exposureMode = 'continuous';
      if (Array.isArray(capabilities.whiteBalanceMode) && capabilities.whiteBalanceMode.includes('continuous')) advanced.whiteBalanceMode = 'continuous';
      if (Object.keys(advanced).length) await track.applyConstraints({ advanced: [advanced] });
    } catch (error) {
      console.info('Continue focus wordt niet door deze camera ondersteund.', error);
    }
  }

  function stopCamera() {
    clearTimeout(state.timer);
    state.timer = 0;
    if (state.stream) state.stream.getTracks().forEach(track => track.stop());
    state.stream = null;
    if (ui.video) ui.video.srcObject = null;
  }

  function scheduleAnalysis() {
    clearTimeout(state.timer);
    if (!state.open || !state.stream || state.processing || state.capturing || ui.cameraScreen.hidden) return;
    state.timer = window.setTimeout(analyseFrame, ANALYSIS_INTERVAL_MS);
  }

  function guideSourceRect() {
    const videoWidth = ui.video.videoWidth;
    const videoHeight = ui.video.videoHeight;
    if (!videoWidth || !videoHeight) return null;
    const shellRect = ui.shell.getBoundingClientRect();
    const guideRect = ui.guide.getBoundingClientRect();
    const scale = Math.max(shellRect.width / videoWidth, shellRect.height / videoHeight);
    const renderedWidth = videoWidth * scale;
    const renderedHeight = videoHeight * scale;
    const hiddenX = (renderedWidth - shellRect.width) / 2;
    const hiddenY = (renderedHeight - shellRect.height) / 2;
    let x = ((guideRect.left - shellRect.left) + hiddenX) / scale;
    let y = ((guideRect.top - shellRect.top) + hiddenY) / scale;
    let width = guideRect.width / scale;
    let height = guideRect.height / scale;
    x = Math.max(0, Math.min(videoWidth - 2, x));
    y = Math.max(0, Math.min(videoHeight - 2, y));
    width = Math.max(2, Math.min(videoWidth - x, width));
    height = Math.max(2, Math.min(videoHeight - y, height));
    return { x, y, width, height };
  }

  function frameMetrics(canvas) {
    const context = canvas.getContext('2d', { willReadFrequently: true });
    const width = canvas.width;
    const height = canvas.height;
    const pixels = context.getImageData(0, 0, width, height).data;
    const luma = new Uint8Array(width * height);
    let sum = 0;
    for (let i = 0, p = 0; i < pixels.length; i += 4, p += 1) {
      const value = Math.round((pixels[i] * .299) + (pixels[i + 1] * .587) + (pixels[i + 2] * .114));
      luma[p] = value;
      sum += value;
    }
    const mean = sum / luma.length;
    let variance = 0;
    let edgeTotal = 0;
    let edgeCount = 0;
    for (let y = 1; y < height; y += 1) {
      for (let x = 1; x < width; x += 1) {
        const index = (y * width) + x;
        const value = luma[index];
        variance += (value - mean) ** 2;
        edgeTotal += Math.abs(value - luma[index - 1]) + Math.abs(value - luma[index - width]);
        edgeCount += 2;
      }
    }
    const contrast = Math.sqrt(variance / Math.max(1, luma.length - width - 1));
    const sharpness = edgeTotal / Math.max(1, edgeCount);
    let motion = 0;
    if (state.previousLuma && state.previousLuma.length === luma.length) {
      let motionTotal = 0;
      for (let index = 0; index < luma.length; index += 4) {
        const currentCentered = luma[index] - mean;
        const previousCentered = state.previousLuma[index] - state.previousMean;
        motionTotal += Math.abs(currentCentered - previousCentered);
      }
      motion = motionTotal / Math.ceil(luma.length / 4);
    }
    state.previousLuma = luma;
    state.previousMean = mean;
    return { mean, contrast, sharpness, motion };
  }

  function classifyFrame(metrics) {
    const warmedUp = performance.now() - state.cameraStartedAt > 650;
    state.motionBaseline = (state.motionBaseline * .94) + (Math.min(metrics.motion || 0, 12) * .06);
    const motionLimit = Math.max(14, state.motionBaseline * 3.4);
    const lightLow = metrics.mean < 48;
    const lightHigh = metrics.mean > 224;
    const hasDetail = metrics.contrast >= 24 && metrics.sharpness >= 8.2;
    const moving = warmedUp && metrics.motion > motionLimit;

    if (!warmedUp) return { quality: 'warn', good: false, text: 'Camera stelt scherp…', title: 'Nog heel even', motionLimit };
    if (lightLow) return { quality: 'bad', good: false, text: 'Meer licht nodig', title: 'Maak de kaart wat lichter', motionLimit };
    if (lightHigh) return { quality: 'bad', good: false, text: 'Te veel licht of reflectie', title: 'Kantel de kaart een klein beetje', motionLimit };
    if (!hasDetail) return { quality: 'warn', good: false, text: 'Vul het kader met de kaart', title: 'Breng de kaart iets dichterbij', motionLimit };
    if (moving) return { quality: 'warn', good: false, text: 'Rustig houden — bijna goed', title: 'Kleine beweging wordt opgevangen', motionLimit, moving: true };
    return { quality: 'good', good: true, text: 'Kaart ligt goed — even vasthouden', title: 'Goed zo, automatische foto volgt', motionLimit };
  }

  function analyseFrame() {
    if (!state.open || !state.stream || state.capturing || state.processing || ui.video.readyState < 2) {
      scheduleAnalysis();
      return;
    }
    const source = guideSourceRect();
    if (!source) {
      scheduleAnalysis();
      return;
    }
    const context = ui.analysisCanvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(ui.video, source.x, source.y, source.width, source.height, 0, 0, ui.analysisCanvas.width, ui.analysisCanvas.height);
    const metrics = frameMetrics(ui.analysisCanvas);
    const classification = classifyFrame(metrics);

    if (classification.good) state.stability = Math.min(1, state.stability + .17);
    else if (classification.moving) state.stability = Math.max(0, state.stability - .04);
    else state.stability = Math.max(0, state.stability - .13);

    ui.lightMetric.textContent = metrics.mean < 48 ? 'Te donker' : metrics.mean > 224 ? 'Te fel' : 'Goed';
    ui.sharpMetric.textContent = metrics.sharpness >= 8.2 && metrics.contrast >= 24 ? 'Scherp' : 'Nog niet';
    ui.motionMetric.textContent = metrics.motion > classification.motionLimit ? 'Beweegt' : 'Rustig';
    ui.qualityTitle.textContent = classification.title;
    setCameraMessage(classification.text, classification.quality);
    updateProgress(state.stability);

    if (state.stability >= AUTO_CAPTURE_SCORE) {
      captureFromCamera(true);
      return;
    }
    scheduleAnalysis();
  }

  function setCameraMessage(text, quality) {
    ui.hintText.textContent = text;
    ui.hint.dataset.quality = quality;
    ui.guide.dataset.quality = quality;
  }

  function updateProgress(value) {
    const progress = Math.max(0, Math.min(1, Number(value) || 0));
    ui.guide.style.setProperty('--scanner-progress', progress);
    ui.qualityPanel.style.setProperty('--scanner-progress', progress);
  }

  function canvasSharpness(canvas) {
    const sample = document.createElement('canvas');
    sample.width = 96;
    sample.height = 134;
    sample.getContext('2d').drawImage(canvas, 0, 0, sample.width, sample.height);
    const metrics = frameMetricsIsolated(sample);
    return metrics.sharpness + (metrics.contrast * .18);
  }

  function frameMetricsIsolated(canvas) {
    const context = canvas.getContext('2d', { willReadFrequently: true });
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const luma = new Uint8Array(canvas.width * canvas.height);
    let sum = 0;
    for (let i = 0, p = 0; i < pixels.length; i += 4, p += 1) {
      luma[p] = Math.round((pixels[i] * .299) + (pixels[i + 1] * .587) + (pixels[i + 2] * .114));
      sum += luma[p];
    }
    const mean = sum / luma.length;
    let variance = 0;
    let edge = 0;
    let count = 0;
    for (let y = 1; y < canvas.height; y += 1) {
      for (let x = 1; x < canvas.width; x += 1) {
        const index = (y * canvas.width) + x;
        variance += (luma[index] - mean) ** 2;
        edge += Math.abs(luma[index] - luma[index - 1]) + Math.abs(luma[index] - luma[index - canvas.width]);
        count += 2;
      }
    }
    return { contrast: Math.sqrt(variance / luma.length), sharpness: edge / Math.max(1, count) };
  }

  function captureCameraFrame() {
    const source = guideSourceRect();
    if (!source) return null;
    const canvas = document.createElement('canvas');
    canvas.width = 630;
    canvas.height = 880;
    canvas.getContext('2d', { alpha: false }).drawImage(
      ui.video,
      source.x, source.y, source.width, source.height,
      0, 0, canvas.width, canvas.height
    );
    return canvas;
  }

  function wait(milliseconds) {
    return new Promise(resolve => window.setTimeout(resolve, milliseconds));
  }

  async function captureFromCamera(automatic) {
    if (state.capturing || state.processing || !state.stream || ui.video.readyState < 2) return;
    state.capturing = true;
    clearTimeout(state.timer);
    ui.guide.dataset.quality = 'capturing';
    ui.qualityTitle.textContent = automatic ? 'Automatische foto wordt genomen' : 'Foto wordt genomen';
    ui.hintText.textContent = 'Blijf nog heel even stil…';
    updateProgress(1);
    try {
      const frames = [];
      for (let index = 0; index < 3; index += 1) {
        if (index) await wait(85);
        const canvas = captureCameraFrame();
        if (canvas) frames.push({ canvas, score: canvasSharpness(canvas) });
      }
      if (!frames.length) throw new Error('Geen camerabeeld beschikbaar.');
      frames.sort((a, b) => b.score - a.score);
      await processCapture(frames[0].canvas);
    } catch (error) {
      console.warn('Foto nemen mislukt:', error);
      state.capturing = false;
      state.stability = 0;
      setCameraMessage('Foto lukte niet — probeer opnieuw', 'bad');
      updateProgress(0);
      scheduleAnalysis();
    }
  }

  async function onPhotoChosen(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = '';
    if (!file || state.processing) return;
    try {
      const canvas = await fileToCardCanvas(file);
      await processCapture(canvas);
    } catch (error) {
      console.warn('Gekozen foto kon niet worden geopend:', error);
      showToast('Deze foto kon niet worden geopend. Probeer een andere foto.');
    }
  }

  function fileToCardCanvas(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = () => {
        URL.revokeObjectURL(url);
        const canvas = document.createElement('canvas');
        canvas.width = 630;
        canvas.height = 880;
        const sourceAspect = image.naturalWidth / image.naturalHeight;
        let sx = 0;
        let sy = 0;
        let sw = image.naturalWidth;
        let sh = image.naturalHeight;
        if (sourceAspect > CARD_ASPECT) {
          sw = sh * CARD_ASPECT;
          sx = (image.naturalWidth - sw) / 2;
        } else {
          sh = sw / CARD_ASPECT;
          sy = (image.naturalHeight - sh) / 2;
        }
        canvas.getContext('2d', { alpha: false }).drawImage(image, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
        resolve(canvas);
      };
      image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Afbeelding laden mislukt.')); };
      image.src = url;
    });
  }

  async function processCapture(canvas) {
    const operation = ++state.operation;
    state.capturing = false;
    state.processing = true;
    state.captureCanvas = canvas;
    state.captureUrl = canvas.toDataURL('image/jpeg', .9);
    state.evidence = null;
    state.ranked = [];
    state.selectedKey = '';
    stopCamera();
    ui.processingImage.src = state.captureUrl;
    ui.resultImage.src = state.captureUrl;
    setProcessStatus('Kaart wordt gelezen…', 'Naam en kaartnummer worden uit de foto gehaald.', 10);
    showScreen('processing');

    try {
      let evidence = await recognizeCard(canvas, operation);
      if (!state.open || operation !== state.operation) return;
      state.evidence = evidence;
      let ranked = Match.rankCards(appCards(), evidence, { limit: 120 });

      if (!ranked[0] || ranked[0].nameScore < .55) {
        setProcessStatus('Naam wordt extra gecontroleerd…', 'Alleen bij een onduidelijke naam volgt een korte tweede lezing.', 48);
        const fallbackName = await recognizeCardName(canvas, operation);
        if (!state.open || operation !== state.operation) return;
        if (fallbackName.text) {
          evidence = {
            ...evidence,
            topText: `${fallbackName.text}\n${evidence.topText || ''}`.trim(),
            fullText: `${fallbackName.text}\n${evidence.fullText || ''}`.trim(),
            topConfidence: Math.max(Number(evidence.topConfidence) || 0, fallbackName.confidence)
          };
          state.evidence = evidence;
          ranked = Match.rankCards(appCards(), evidence, { limit: 120 });
        }
      }

      setProcessStatus('Beste kaarten worden vergeleken…', 'Alleen de meest logische afbeeldingen worden nog gecontroleerd.', 62);
      const textConfidence = Match.confidenceFor(ranked);
      const trustedFraction = ranked[0] && ranked[0].numberEvidence && ranked[0].numberEvidence.kind === 'fraction';
      const canSkipVisual = textConfidence.autoSelect && trustedFraction && Number(evidence.bottomConfidence || 0) >= 52;
      const visualCandidates = canSkipVisual ? [] : selectVisualCandidates(ranked);
      let visualScores = {};
      if (visualCandidates.length) {
        visualScores = await compareCandidateImages(canvas, visualCandidates, operation);
        if (!state.open || operation !== state.operation) return;
        ranked = Match.rankCards(appCards(), evidence, { limit: 8, visualScores });
      } else {
        ranked = ranked.slice(0, 8);
      }
      state.ranked = ranked;
      setProcessStatus('Resultaat klaar', 'De beste overeenkomsten zijn gevonden.', 100);
      await wait(180);
      if (!state.open || operation !== state.operation) return;
      renderResults();
      showScreen('results');
    } catch (error) {
      console.warn('Automatische herkenning mislukt:', error);
      if (!state.open || operation !== state.operation) return;
      state.evidence = { topText: '', bottomText: '', fullText: '', error: String(error && error.message || error) };
      state.ranked = [];
      renderResults();
      showScreen('results');
    } finally {
      if (operation === state.operation) state.processing = false;
    }
  }

  function setProcessStatus(title, text, progress) {
    ui.processingTitle.textContent = title;
    ui.processingText.textContent = text;
    ui.processFill.style.setProperty('--process-progress', `${Math.max(0, Math.min(100, progress))}%`);
  }

  function loadTesseract() {
    if (window.Tesseract) return Promise.resolve(window.Tesseract);
    if (window.__pokemonTesseractPromise) return window.__pokemonTesseractPromise;
    window.__pokemonTesseractPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = TESSERACT_URL;
      script.async = true;
      script.crossOrigin = 'anonymous';
      script.onload = () => window.Tesseract ? resolve(window.Tesseract) : reject(new Error('OCR-bibliotheek ontbreekt.'));
      script.onerror = () => reject(new Error('OCR kon niet worden geladen. Controleer je internetverbinding.'));
      document.head.appendChild(script);
    });
    return window.__pokemonTesseractPromise;
  }

  async function getOcrWorker(operation) {
    if (state.ocrWorker) return state.ocrWorker;
    if (!state.ocrWarmPromise) {
      state.ocrWarmPromise = (async () => {
        const Tesseract = await loadTesseract();
        const worker = await Tesseract.createWorker('eng', 1, {
          logger(message) {
            if (!state.processing || !message) return;
            const base = message.status === 'recognizing text' ? 22 : 12;
            const progress = base + Math.round((Number(message.progress) || 0) * 28);
            ui.processFill.style.setProperty('--process-progress', `${Math.min(58, progress)}%`);
          }
        });
        state.ocrWorker = worker;
        return worker;
      })();
    }
    try {
      return await state.ocrWarmPromise;
    } catch (error) {
      state.ocrWarmPromise = null;
      throw error;
    }
  }

  function warmOcrWorker() {
    if (state.ocrWorker || state.ocrWarmPromise) return;
    getOcrWorker(state.operation).catch(error => {
      console.info('OCR wordt pas bij de foto geladen.', error);
    });
  }

  function makeOcrCrop(source, crop, targetWidth) {
    const canvas = document.createElement('canvas');
    const sourceX = Math.round(source.width * crop.x);
    const sourceY = Math.round(source.height * crop.y);
    const sourceWidth = Math.round(source.width * crop.width);
    const sourceHeight = Math.round(source.height * crop.height);
    const scale = Math.min(2.2, Math.max(1, Number(targetWidth || 960) / sourceWidth));
    canvas.width = Math.max(1, Math.round(sourceWidth * scale));
    canvas.height = Math.max(1, Math.round(sourceHeight * scale));
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(source, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    let min = 255;
    let max = 0;
    for (let index = 0; index < pixels.data.length; index += 4) {
      const gray = (pixels.data[index] * .299) + (pixels.data[index + 1] * .587) + (pixels.data[index + 2] * .114);
      min = Math.min(min, gray);
      max = Math.max(max, gray);
    }
    const range = Math.max(38, max - min);
    for (let index = 0; index < pixels.data.length; index += 4) {
      const gray = (pixels.data[index] * .299) + (pixels.data[index + 1] * .587) + (pixels.data[index + 2] * .114);
      const normalized = Math.max(0, Math.min(255, ((gray - min) / range) * 255));
      const boosted = Math.max(0, Math.min(255, ((normalized - 128) * 1.16) + 128));
      pixels.data[index] = boosted;
      pixels.data[index + 1] = boosted;
      pixels.data[index + 2] = boosted;
      pixels.data[index + 3] = 255;
    }
    context.putImageData(pixels, 0, 0);
    return canvas;
  }

  function makeFastOcrComposite(source) {
    const nameCrop = makeOcrCrop(source, { x: .018, y: .012, width: .964, height: .13 }, 960);
    const footerCrop = makeOcrCrop(source, { x: .018, y: .875, width: .964, height: .105 }, 960);
    const gap = 28;
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(nameCrop.width, footerCrop.width);
    canvas.height = nameCrop.height + gap + footerCrop.height;
    const context = canvas.getContext('2d', { alpha: false });
    context.fillStyle = '#fff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(nameCrop, 0, 0);
    context.drawImage(footerCrop, 0, nameCrop.height + gap);
    return { canvas, dividerY: nameCrop.height + (gap / 2) };
  }

  function wordsForOcrRegion(words, predicate) {
    return (words || [])
      .filter(word => word && word.text && word.bbox && predicate((Number(word.bbox.y0) + Number(word.bbox.y1)) / 2))
      .map(word => String(word.text).trim())
      .filter(Boolean)
      .join(' ');
  }

  function splitCompositeOcr(result, dividerY) {
    const data = result && result.data || {};
    const fullText = String(data.text || '').trim();
    const words = Array.isArray(data.words) ? data.words : [];
    let topText = wordsForOcrRegion(words, y => y < dividerY);
    let bottomText = wordsForOcrRegion(words, y => y >= dividerY);
    if (!topText) {
      const lines = fullText.split(/\n+/).map(line => line.trim()).filter(Boolean);
      const splitAt = Math.max(1, Math.min(2, Math.ceil(lines.length / 2)));
      topText = lines.slice(0, splitAt).join(' ');
      bottomText = bottomText || lines.slice(splitAt).join(' ');
    }
    return { topText, bottomText, fullText: `${topText}\n${bottomText}`.trim() || fullText };
  }

  async function recognizeCard(canvas, operation) {
    const worker = await getOcrWorker(operation);
    if (operation !== state.operation) throw new Error('Scan geannuleerd.');
    const composite = makeFastOcrComposite(canvas);

    setProcessStatus('Naam en nummer worden gelezen…', 'Een compacte scan controleert beide zones tegelijk.', 30);
    await worker.setParameters({ tessedit_pageseg_mode: '6', preserve_interword_spaces: '1' });
    const result = await worker.recognize(composite.canvas);
    if (operation !== state.operation) throw new Error('Scan geannuleerd.');
    const parsed = splitCompositeOcr(result, composite.dividerY);
    const confidence = Number(result && result.data && result.data.confidence || 0);
    return {
      topText: parsed.topText,
      bottomText: parsed.bottomText,
      fullText: parsed.fullText,
      topConfidence: confidence,
      bottomConfidence: confidence
    };
  }

  async function recognizeCardName(canvas, operation) {
    const worker = await getOcrWorker(operation);
    if (operation !== state.operation) throw new Error('Scan geannuleerd.');
    const nameCrop = makeOcrCrop(canvas, { x: .025, y: .012, width: .95, height: .13 }, 1040);
    await worker.setParameters({
      tessedit_pageseg_mode: '7',
      preserve_interword_spaces: '1',
      tessedit_char_whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.'- "
    });
    let result;
    try {
      result = await worker.recognize(nameCrop);
    } finally {
      await worker.setParameters({ tessedit_char_whitelist: '', tessedit_pageseg_mode: '6' });
    }
    if (operation !== state.operation) throw new Error('Scan geannuleerd.');
    return {
      text: String(result && result.data && result.data.text || '').trim(),
      confidence: Number(result && result.data && result.data.confidence || 0)
    };
  }

  function fingerprintRegion(source, crop, width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    const sourceWidth = source.width || source.naturalWidth;
    const sourceHeight = source.height || source.naturalHeight;
    const sourceX = sourceWidth * crop.x;
    const sourceY = sourceHeight * crop.y;
    context.drawImage(source, sourceX, sourceY, sourceWidth * crop.width, sourceHeight * crop.height, 0, 0, canvas.width, canvas.height);
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const color = [];
    const light = [];
    const channels = [[], [], []];
    let lightTotal = 0;
    for (let index = 0; index < data.length; index += 4) {
      const red = data[index];
      const green = data[index + 1];
      const blue = data[index + 2];
      const total = Math.max(24, red + green + blue);
      color.push(red / total, green / total, blue / total);
      channels[0].push(red);
      channels[1].push(green);
      channels[2].push(blue);
      const luma = (red * .299) + (green * .587) + (blue * .114);
      light.push(luma);
      lightTotal += luma;
    }
    const mean = lightTotal / light.length;
    const deviation = Math.sqrt(light.reduce((total, value) => total + ((value - mean) ** 2), 0) / light.length) || 1;
    const channelStats = channels.map(values => {
      const channelMean = values.reduce((total, value) => total + value, 0) / values.length;
      const channelDeviation = Math.sqrt(values.reduce((total, value) => total + ((value - channelMean) ** 2), 0) / values.length) || 1;
      return { mean: channelMean, deviation: channelDeviation };
    });
    const normalizedRgb = [];
    for (let index = 0; index < channels[0].length; index += 1) {
      for (let channel = 0; channel < 3; channel += 1) {
        normalizedRgb.push((channels[channel][index] - channelStats[channel].mean) / channelStats[channel].deviation);
      }
    }
    return { color, light: light.map(value => (value - mean) / deviation), normalizedRgb };
  }

  function fingerprint(source) {
    return {
      full: fingerprintRegion(source, { x: .025, y: .018, width: .95, height: .964 }, 24, 34),
      art: fingerprintRegion(source, { x: .075, y: .115, width: .85, height: .39 }, 28, 14)
    };
  }

  function compareFingerprintRegion(left, right) {
    if (!left || !right || left.light.length !== right.light.length) return 0;
    let lightDifference = 0;
    let colorDifference = 0;
    let rgbDifference = 0;
    for (let index = 0; index < left.light.length; index += 1) {
      lightDifference += Math.min(3, Math.abs(left.light[index] - right.light[index])) / 3;
    }
    for (let index = 0; index < left.color.length; index += 1) {
      colorDifference += Math.min(.55, Math.abs(left.color[index] - right.color[index])) / .55;
    }
    for (let index = 0; index < left.normalizedRgb.length; index += 1) {
      rgbDifference += Math.min(3, Math.abs(left.normalizedRgb[index] - right.normalizedRgb[index])) / 3;
    }
    lightDifference /= left.light.length;
    colorDifference /= left.color.length;
    rgbDifference /= left.normalizedRgb.length;
    return Math.max(0, Math.min(1, 1 - ((lightDifference * .42) + (colorDifference * .23) + (rgbDifference * .35))));
  }

  function compareFingerprints(left, right) {
    if (!left || !right || !left.full || !right.full) return 0;
    const fullScore = compareFingerprintRegion(left.full, right.full);
    const artScore = compareFingerprintRegion(left.art, right.art);
    return (fullScore * .38) + (artScore * .62);
  }

  function getImageCandidates(card) {
    try {
      if (typeof imageCandidatesFor === 'function') return imageCandidatesFor(card) || [];
    } catch (_) {}
    return [card && card.imageUrl].filter(Boolean);
  }

  function lightweightImageUrl(url) {
    const value = String(url || '');
    if (value.includes('images.pokemontcg.io/')) return value.replace('_hires.png', '.png');
    return value;
  }

  async function loadImageForFingerprint(url) {
    const controller = 'AbortController' in window ? new AbortController() : null;
    const timeout = window.setTimeout(() => { if (controller) controller.abort(); }, IMAGE_FETCH_TIMEOUT_MS);
    try {
      const response = await fetch(lightweightImageUrl(url), {
        mode: 'cors',
        cache: 'force-cache',
        signal: controller ? controller.signal : undefined
      });
      if (!response.ok) throw new Error(`Afbeelding ${response.status}`);
      const blob = await response.blob();
      if ('createImageBitmap' in window) return window.createImageBitmap(blob);
      return await new Promise((resolve, reject) => {
        const objectUrl = URL.createObjectURL(blob);
        const image = new Image();
        image.onload = () => { URL.revokeObjectURL(objectUrl); resolve(image); };
        image.onerror = () => { URL.revokeObjectURL(objectUrl); reject(new Error('Afbeelding laden mislukt.')); };
        image.src = objectUrl;
      });
    } finally {
      clearTimeout(timeout);
    }
  }

  async function fingerprintForUrl(url) {
    const key = lightweightImageUrl(url);
    if (visualFingerprintCache.has(key)) return visualFingerprintCache.get(key);
    const pending = (async () => {
      const image = await loadImageForFingerprint(key);
      try {
        return fingerprint(image);
      } finally {
        if (typeof image.close === 'function') image.close();
      }
    })();
    visualFingerprintCache.set(key, pending);
    if (visualFingerprintCache.size > 96) {
      const oldest = visualFingerprintCache.keys().next().value;
      if (oldest && oldest !== key) visualFingerprintCache.delete(oldest);
    }
    try {
      return await pending;
    } catch (error) {
      visualFingerprintCache.delete(key);
      throw error;
    }
  }

  async function visualScoreForCard(captureFingerprint, card) {
    const candidates = [...new Set(getImageCandidates(card).map(lightweightImageUrl))].slice(0, 2);
    let best = 0;
    for (const url of candidates) {
      try {
        best = Math.max(best, compareFingerprints(captureFingerprint, await fingerprintForUrl(url)));
        // Kandidaten voor dezelfde kaart tonen vrijwel altijd exact dezelfde druk.
        // Na de eerste werkende afbeelding is een tweede download dus alleen vertraging.
        break;
      } catch (_) {}
    }
    return best;
  }

  function selectVisualCandidates(ranked) {
    const rows = Array.isArray(ranked) ? ranked : [];
    const top = rows[0];
    if (!top) return [];
    if (top.nameScore >= .55) {
      const nameFloor = Math.max(.44, top.nameScore - .2);
      const named = rows.filter(row => row.nameScore >= nameFloor);
      if (named.length) return named.slice(0, 14);
    }
    return rows.filter(row => row.score >= 22).slice(0, 8);
  }

  async function compareCandidateImages(canvas, candidates, operation) {
    const captureFingerprint = fingerprint(canvas);
    const scores = {};
    let cursor = 0;
    const workers = Array.from({ length: Math.min(4, candidates.length) }, async () => {
      while (cursor < candidates.length) {
        const index = cursor;
        cursor += 1;
        const row = candidates[index];
        scores[row.card.key] = await visualScoreForCard(captureFingerprint, row.card);
        if (operation === state.operation) {
          const progress = 64 + Math.round(((index + 1) / candidates.length) * 30);
          ui.processFill.style.setProperty('--process-progress', `${Math.min(94, progress)}%`);
        }
      }
    });
    await Promise.all(workers);
    return scores;
  }

  function evidenceSummary() {
    const evidence = state.evidence || {};
    const combined = `${evidence.topText || ''} ${evidence.bottomText || ''}`.replace(/\s+/g, ' ').trim();
    if (!combined) return 'Tekst was niet duidelijk genoeg. Zoek hieronder op naam, set of kaartnummer.';
    const shortened = combined.length > 105 ? `${combined.slice(0, 102)}…` : combined;
    return `Gelezen: “${shortened}”`;
  }

  function renderResults() {
    const confidence = Match.confidenceFor(state.ranked);
    ui.resultText.textContent = evidenceSummary();
    ui.confidence.className = `scanner-confidence-pill ${confidence.level}`;
    ui.confidence.textContent = confidence.label;
    if (confidence.level === 'high') ui.resultTitle.textContent = 'Kaart vrijwel zeker gevonden';
    else if (state.ranked.length) ui.resultTitle.textContent = 'Controleer de beste overeenkomsten';
    else ui.resultTitle.textContent = 'Nog geen betrouwbare kaart gevonden';

    state.selectedKey = confidence.autoSelect && state.ranked[0] ? state.ranked[0].card.key : '';
    renderCandidateList();
    renderSelection();
  }

  function imageUrlForScanner(card) {
    return getImageCandidates(card)[0] || '';
  }

  function renderCandidateList() {
    if (!state.ranked.length) {
      ui.candidateList.innerHTML = '<div class="scanner-no-match"><b>Geen zekere overeenkomst.</b><br>Vul hierboven een deel van de kaartnaam, set of het kaartnummer in. De scanner kiest bewust geen willekeurige kaart.</div>';
      return;
    }
    ui.candidateList.innerHTML = state.ranked.map(row => {
      const card = row.card;
      const selected = card.key === state.selectedKey;
      const imageUrl = imageUrlForScanner(card);
      const percent = Math.max(1, Math.min(99, Math.round(row.score)));
      const image = imageUrl
        ? `<img src="${escapeHtml(imageUrl)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">`
        : '<span class="scanner-candidate-image-placeholder">Geen<br>afbeelding</span>';
      return `<button type="button" class="scanner-candidate${selected ? ' selected' : ''}" data-scanner-card-key="${escapeHtml(card.key)}">
        ${image}
        <span class="scanner-candidate-copy"><b>${escapeHtml(card.name)}</b><span>${escapeHtml(card.set)} · #${escapeHtml(card.num)}</span><small>${escapeHtml(Match.reasonFor(row))}</small></span>
        <span class="scanner-candidate-score"><b>${percent}%</b><span>match</span><i class="scanner-choice-dot">✓</i></span>
      </button>`;
    }).join('');
  }

  function selectedResult() {
    return state.ranked.find(row => row.card.key === state.selectedKey) || null;
  }

  function selectCandidate(key) {
    if (!state.ranked.some(row => row.card.key === key)) return;
    state.selectedKey = key;
    state.quantity = 1;
    renderCandidateList();
    renderSelection();
    window.setTimeout(() => ui.selection.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 30);
  }

  function renderSelection() {
    const result = selectedResult();
    ui.selection.hidden = !result;
    if (!result) return;
    const card = result.card;
    ui.selectedImage.src = imageUrlForScanner(card) || state.captureUrl;
    ui.selectedName.textContent = card.name;
    ui.selectedMeta.textContent = `${card.set} · #${card.num}`;
    setVariant(state.variant);
    setQuantity(state.quantity);
  }

  function setVariant(variant) {
    state.variant = ['Normal', 'Reverse Holo', 'Holo'].includes(variant) ? variant : 'Normal';
    if (!ui.root) return;
    ui.root.querySelectorAll('[data-scanner-variant]').forEach(button => {
      button.classList.toggle('active', button.dataset.scannerVariant === state.variant);
    });
  }

  function setQuantity(value) {
    state.quantity = Math.max(1, Math.min(99, Number(value) || 1));
    if (ui.qtyValue) ui.qtyValue.textContent = String(state.quantity);
  }

  function refineCandidates() {
    const query = Match.normalizeText(ui.refineInput.value);
    if (!query) {
      renderResults();
      return;
    }
    const compactQuery = query.replace(/\s+/g, '');
    const results = appCards().map(card => {
      const name = Match.normalizeText(card.name);
      const set = Match.normalizeText(card.set);
      const series = Match.normalizeText(card.series);
      const abbr = Match.normalizeText(card.abbr);
      const number = Match.normalizeCardNumber(card.num);
      let score = 0;
      if (name === query) score += 90;
      else if (name.startsWith(query)) score += 72;
      else if (name.includes(query)) score += 58;
      else score += Match.nameSimilarity(query, card.name) * 45;
      if (set.includes(query) || series.includes(query)) score += 42;
      if (abbr === compactQuery) score += 54;
      if (number === Match.normalizeCardNumber(compactQuery)) score += 52;
      return {
        card,
        score,
        nameScore: name.includes(query) ? 1 : Match.nameSimilarity(query, card.name),
        numberScore: number === Match.normalizeCardNumber(compactQuery) ? 1 : 0,
        effectiveNumberScore: number === Match.normalizeCardNumber(compactQuery) ? 1 : 0,
        numberEvidence: number === Match.normalizeCardNumber(compactQuery) ? { normalized: number } : null,
        setScore: set.includes(query) || abbr === compactQuery ? 1 : 0,
        visualScore: 0,
        usefulVisual: 0,
        visualRelative: 0,
        visualEvaluated: false,
        onlyNumber: false,
        signals: ['manual']
      };
    }).filter(row => row.score >= 30).sort((a, b) => b.score - a.score).slice(0, 12);
    state.ranked = results;
    state.selectedKey = '';
    ui.confidence.className = 'scanner-confidence-pill low';
    ui.confidence.textContent = results.length ? 'Kies zelf de juiste kaart' : 'Geen kaart gevonden';
    ui.resultTitle.textContent = results.length ? `${results.length} zoekresultaten` : 'Geen resultaat voor deze zoekterm';
    renderCandidateList();
    renderSelection();
  }

  function updateBatchAction() {
    if (!ui.batchTop) return;
    const count = state.batchItems.length;
    ui.batchTop.hidden = count === 0;
    ui.batchBadge.textContent = String(count);
    ui.batchTop.setAttribute('aria-label', `${count} toegevoegde ${count === 1 ? 'kaart' : 'kaarten'} bekijken`);
  }

  function addCardToBatch(card, quantity) {
    const existing = state.batchItems.find(item => item.card.key === card.key);
    if (existing) existing.quantity += quantity;
    else state.batchItems.push({ card, quantity, imageUrl: imageUrlForScanner(card) || state.captureUrl });
    state.batchCount += quantity;
    updateBatchAction();
  }

  function renderBatchSummary() {
    const differentCards = state.batchItems.length;
    const totalCards = state.batchCount;
    const visibleCards = state.batchItems.slice(0, 3);
    ui.batchCards.innerHTML = visibleCards.map((item, index) => {
      const imageUrl = item.imageUrl || state.captureUrl;
      return imageUrl
        ? `<img src="${escapeHtml(imageUrl)}" alt="" style="--scanner-card-index:${index}" onerror="this.style.visibility='hidden'">`
        : '';
    }).join('');
    ui.batchTitle.textContent = `${totalCards} ${totalCards === 1 ? 'kaart' : 'kaarten'} toegevoegd`;
    const differentLabel = differentCards === 1 ? '1 kaart' : `${differentCards} verschillende kaarten`;
    ui.batchText.textContent = `${differentLabel} uit deze scanronde. Alles staat in je collectie en gaat mee in je back-up en online synchronisatie.`;
  }

  function showBatchSummary() {
    if (!state.batchItems.length) return;
    state.operation += 1;
    state.processing = false;
    state.capturing = false;
    stopCamera();
    renderBatchSummary();
    showScreen('batch');
  }

  function openCollectionFromScanner() {
    closeScanner();
    try {
      if (typeof navigateToTab === 'function') navigateToTab('collection');
    } catch (_) {}
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function saveSelectedCard() {
    const result = selectedResult();
    if (!result) return;
    const card = result.card;
    try {
      let alreadyOwned = false;
      try { alreadyOwned = typeof isOwned === 'function' ? isOwned(card) : false; } catch (_) {}
      let existingQuantity = alreadyOwned ? 1 : 0;
      try {
        if (typeof detailsFor === 'function') existingQuantity = Number(detailsFor(card).quantity) || existingQuantity;
      } catch (_) {}
      try {
        if (typeof setOwned === 'function') setOwned(card, true);
        else if (typeof owned !== 'undefined') owned[card.key] = true;
      } catch (_) {}
      try {
        if (typeof setDetailsFor === 'function') {
          setDetailsFor(card, { variant: state.variant, quantity: existingQuantity + state.quantity });
        }
      } catch (_) {}
      try { if (typeof saveOwned === 'function') saveOwned(); } catch (_) {}
      try { if (typeof render === 'function') render(); } catch (_) {}
      addCardToBatch(card, state.quantity);
      const variantLabel = state.variant === 'Normal' ? 'normaal' : state.variant === 'Reverse Holo' ? 'reverse' : 'holo';
      showToast(`${card.name} is toegevoegd (${variantLabel}, +${state.quantity}).`);
      window.setTimeout(resetToCamera, 420);
    } catch (error) {
      console.error('Kaart opslaan vanuit scanner mislukt:', error);
      showToast('Opslaan lukte niet. Probeer de kaart via de zoeklijst toe te voegen.');
    }
  }

  function showToast(message) {
    if (!ui.toast) return;
    clearTimeout(state.toastTimer);
    ui.toast.textContent = message;
    ui.toast.classList.add('show');
    state.toastTimer = window.setTimeout(() => ui.toast.classList.remove('show'), 2400);
  }

  function init() {
    buildScanner();
    addLaunchers();
    window.PokemonCardScanner = {
      open: openScanner,
      close: closeScanner,
      analyseFrameMetrics: frameMetricsIsolated,
      compareFingerprints,
      version: SCANNER_VERSION
    };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
