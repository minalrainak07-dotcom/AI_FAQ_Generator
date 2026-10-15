/**
 * AI FAQ GENERATOR - Application Client JavaScript
 * Handles PDF extraction, FAQ generation, accordion rendering, search/filtering,
 * inline/modal editing, history operations, exports, and toast alerts.
 */

(function () {
  'use strict';

  // --- STATE MANAGEMENT ---
  const state = {
    pdfFile: null,
    extractedPdfText: '',
    currentGeneration: null, // Holds the active generation object
    activeTab: 'pdf' // 'pdf', 'text', or 'topic'
  };

  // ==========================================
  // UTILITY FUNCTIONS
  // ==========================================

  /**
   * Display a Bootstrap Toast message
   * @param {string} message - Message content
   * @param {'success'|'danger'|'error'|'warning'|'info'} type - Toast type
   */
  function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const normalizedType = (type === 'error') ? 'danger' : type;
    const icons = {
      success: 'fa-circle-check',
      danger: 'fa-circle-exclamation',
      warning: 'fa-triangle-exclamation',
      info: 'fa-circle-info'
    };
    const iconClass = icons[normalizedType] || 'fa-circle-info';

    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-bg-${normalizedType} border-0 shadow-lg mb-2`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');

    toastEl.innerHTML = `
      <div class="d-flex">
        <div class="toast-body d-flex align-items-center gap-2">
          <i class="fa-solid ${iconClass}"></i>
          <span>${escapeHtml(message)}</span>
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    `;

    container.appendChild(toastEl);
    if (window.bootstrap && window.bootstrap.Toast) {
      const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
      toast.show();
      toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    } else {
      setTimeout(() => toastEl.remove(), 4000);
    }
  }

  /**
   * Escape HTML to prevent XSS
   */
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /**
   * Format file size in KB or MB
   */
  function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 KB';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  /**
   * Format ISO date string nicely
   */
  function formatDate(dateString) {
    if (!dateString) return 'Just now';
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) return dateString;
      return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch (e) {
      return dateString;
    }
  }

  /**
   * Show global loading overlay
   */
  function showLoading(title = 'Generating FAQs...', subtitle = 'This may take a moment while AI processes your input.') {
    const overlay = document.getElementById('loadingOverlay');
    const titleEl = document.getElementById('loadingTitle');
    const subtitleEl = document.getElementById('loadingSubtitle');
    if (titleEl) titleEl.textContent = title;
    if (subtitleEl) subtitleEl.textContent = subtitle;
    if (overlay) overlay.classList.remove('d-none');
  }

  /**
   * Hide global loading overlay
   */
  function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.classList.add('d-none');
  }

  /**
   * Copy plain text to clipboard
   */
  function copyToClipboard(text, successMsg = 'Copied to clipboard!') {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        showToast(successMsg, 'success');
      }).catch(() => {
        fallbackCopyToClipboard(text, successMsg);
      });
    } else {
      fallbackCopyToClipboard(text, successMsg);
    }
  }

  /**
   * Fallback for copying to clipboard
   */
  function fallbackCopyToClipboard(text, successMsg) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      const successful = document.execCommand('copy');
      if (successful) {
        showToast(successMsg, 'success');
      } else {
        showToast('Unable to copy text', 'warning');
      }
    } catch (err) {
      showToast('Copy failed', 'danger');
    }
    document.body.removeChild(textArea);
  }

  /**
   * Confirm prompt helper
   */
  function confirmAction(message) {
    return window.confirm(message);
  }

  // ==========================================
  // PAGE 1: GENERATE PAGE LOGIC
  // ==========================================

  function initGeneratePage() {
    const generateBtn = document.getElementById('generateFaqBtn');
    if (!generateBtn) return; // Not on generate page

    // 1. Initialize URL Query parameter tab selection
    const urlParams = new URLSearchParams(window.location.search);
    const requestedTab = urlParams.get('tab');
    if (requestedTab) {
      const tabTrigger = document.querySelector(`#pills-${requestedTab}-tab`);
      if (tabTrigger && window.bootstrap && window.bootstrap.Tab) {
        const tabInstance = new bootstrap.Tab(tabTrigger);
        tabInstance.show();
        state.activeTab = requestedTab;
        updateActiveTabLabel(requestedTab);
      }
    }

    // 2. Tab change listener
    const tabButtons = document.querySelectorAll('#sourceMethodTabs button[data-bs-toggle="pill"]');
    tabButtons.forEach(btn => {
      btn.addEventListener('shown.bs.tab', function (e) {
        const source = e.target.getAttribute('data-source') || 'pdf';
        state.activeTab = source;
        updateActiveTabLabel(source);
      });
    });

    function updateActiveTabLabel(source) {
      const label = document.getElementById('activeTabLabel');
      if (label) {
        if (source === 'pdf') label.textContent = 'PDF Upload';
        else if (source === 'text') label.textContent = 'Paste Text';
        else if (source === 'topic') label.textContent = 'Enter Topic';
      }
    }

    // 3. PDF Drag and Drop Setup
    const dropZone = document.getElementById('pdfDropZone');
    const fileInput = document.getElementById('pdfFileInput');
    const browseBtn = document.getElementById('browsePdfBtn');
    const removePdfBtn = document.getElementById('removePdfBtn');
    const extractPdfBtn = document.getElementById('extractPdfBtn');

    if (dropZone && fileInput) {
      browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
      });

      dropZone.addEventListener('click', () => {
        fileInput.click();
      });

      ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropZone.classList.add('dragover');
        }, false);
      });

      ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          dropZone.classList.remove('dragover');
        }, false);
      });

      dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
          handleSelectedPdf(files[0]);
        }
      });

      fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
          handleSelectedPdf(e.target.files[0]);
        }
      });
    }

    function handleSelectedPdf(file) {
      // Validate file extension
      if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') {
        showToast('Please select a valid PDF document (.pdf)', 'warning');
        return;
      }

      // Validate size (10 MB = 10 * 1024 * 1024 bytes)
      const maxSize = 10 * 1024 * 1024;
      if (file.size > maxSize) {
        showToast('File size exceeds the 10MB limit. Please choose a smaller PDF.', 'danger');
        return;
      }

      state.pdfFile = file;
      state.extractedPdfText = '';

      // Update UI
      const nameEl = document.getElementById('pdfFileName');
      const sizeEl = document.getElementById('pdfFileSize');
      const cardEl = document.getElementById('pdfSelectedCard');
      const extractResultEl = document.getElementById('pdfExtractionResult');

      if (nameEl) nameEl.textContent = file.name;
      if (sizeEl) sizeEl.textContent = formatFileSize(file.size);
      if (cardEl) cardEl.classList.remove('d-none');
      if (extractResultEl) extractResultEl.classList.add('d-none');

      showToast(`Selected "${file.name}" (${formatFileSize(file.size)})`, 'info');
    }

    if (removePdfBtn) {
      removePdfBtn.addEventListener('click', () => {
        state.pdfFile = null;
        state.extractedPdfText = '';
        if (fileInput) fileInput.value = '';
        const cardEl = document.getElementById('pdfSelectedCard');
        const extractResultEl = document.getElementById('pdfExtractionResult');
        if (cardEl) cardEl.classList.add('d-none');
        if (extractResultEl) extractResultEl.classList.add('d-none');
        showToast('PDF removed', 'info');
      });
    }

    // Extract Text from PDF via API
    if (extractPdfBtn) {
      extractPdfBtn.addEventListener('click', async () => {
        if (!state.pdfFile) {
          showToast('Please choose a PDF file first.', 'warning');
          return;
        }

        extractPdfBtn.disabled = true;
        extractPdfBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Extracting...';

        const formData = new FormData();
        formData.append('file', state.pdfFile);

        try {
          const response = await fetch('/api/upload-pdf', {
            method: 'POST',
            body: formData
          });

          const data = await response.json();

          if (response.ok && data.success) {
            state.extractedPdfText = data.text || '';
            const wordCount = data.word_count || (data.text ? data.text.trim().split(/\s+/).length : 0);

            const resultContainer = document.getElementById('pdfExtractionResult');
            const statusText = document.getElementById('pdfExtractStatusText');
            const previewTextarea = document.getElementById('pdfExtractedTextPreview');

            if (statusText) statusText.textContent = `Extracted ${wordCount.toLocaleString()} words successfully!`;
            if (previewTextarea) previewTextarea.value = state.extractedPdfText;
            if (resultContainer) resultContainer.classList.remove('d-none');

            showToast('Text extracted successfully from PDF!', 'success');
          } else {
            showToast(data.error || 'Failed to extract text from PDF.', 'danger');
          }
        } catch (err) {
          showToast('Network error while extracting text from PDF.', 'danger');
        } finally {
          extractPdfBtn.disabled = false;
          extractPdfBtn.innerHTML = '<i class="fa-solid fa-file-import me-1"></i> Extract Text';
        }
      });
    }

    // 4. Text Input & Word/Character Counting
    const textInput = document.getElementById('textInput');
    const charCountEl = document.getElementById('charCount');
    const wordCountEl = document.getElementById('wordCount');
    const clearTextBtn = document.getElementById('clearTextBtn');

    if (textInput) {
      textInput.addEventListener('input', () => {
        const text = textInput.value;
        const chars = text.length;
        const words = text.trim() === '' ? 0 : text.trim().split(/\s+/).length;
        if (charCountEl) charCountEl.textContent = chars.toLocaleString();
        if (wordCountEl) wordCountEl.textContent = words.toLocaleString();
      });
    }

    if (clearTextBtn && textInput) {
      clearTextBtn.addEventListener('click', () => {
        textInput.value = '';
        if (charCountEl) charCountEl.textContent = '0';
        if (wordCountEl) wordCountEl.textContent = '0';
        textInput.focus();
      });
    }

    // 5. Topic Suggestions Buttons
    const topicInput = document.getElementById('topicInput');
    const topicTags = document.querySelectorAll('.topic-tag-btn');
    topicTags.forEach(btn => {
      btn.addEventListener('click', () => {
        const topic = btn.getAttribute('data-topic');
        if (topicInput && topic) {
          topicInput.value = topic;
          topicInput.focus();
          showToast(`Topic selected: "${topic}"`, 'info');
        }
      });
    });

    // 6. Settings Change & Live Summary Update
    const numFaqsRadios = document.querySelectorAll('input[name="numFaqs"]');
    const difficultySelect = document.getElementById('difficultySelect');
    const answerLengthSelect = document.getElementById('answerLengthSelect');
    const languageSelect = document.getElementById('languageSelect');
    const categorySelect = document.getElementById('categorySelect');

    function updateSettingsSummary() {
      let numFaqs = '5';
      numFaqsRadios.forEach(radio => {
        if (radio.checked) numFaqs = radio.value;
      });

      const badgeNumFaqs = document.getElementById('numFaqsBadge');
      if (badgeNumFaqs) badgeNumFaqs.textContent = `${numFaqs} FAQs`;

      const sumCount = document.getElementById('summaryBadgeCount');
      const sumDiff = document.getElementById('summaryBadgeDifficulty');
      const sumLen = document.getElementById('summaryBadgeLength');
      const sumLang = document.getElementById('summaryBadgeLanguage');
      const sumCat = document.getElementById('summaryBadgeCategory');

      if (sumCount) sumCount.textContent = `${numFaqs} FAQs`;
      if (sumDiff && difficultySelect) sumDiff.textContent = difficultySelect.value;
      if (sumLen && answerLengthSelect) sumLen.textContent = `${answerLengthSelect.value} Length`;
      if (sumLang && languageSelect) sumLang.textContent = languageSelect.value;
      if (sumCat && categorySelect) sumCat.textContent = categorySelect.value;
    }

    numFaqsRadios.forEach(r => r.addEventListener('change', updateSettingsSummary));
    if (difficultySelect) difficultySelect.addEventListener('change', updateSettingsSummary);
    if (answerLengthSelect) answerLengthSelect.addEventListener('change', updateSettingsSummary);
    if (languageSelect) languageSelect.addEventListener('change', updateSettingsSummary);
    if (categorySelect) categorySelect.addEventListener('change', updateSettingsSummary);

    // Initial sync
    updateSettingsSummary();

    // 7. Form Submission: FAQ Generation Action
    generateBtn.addEventListener('click', async (e) => {
      e.preventDefault();

      // Gather settings
      let numFaqs = 5;
      numFaqsRadios.forEach(radio => {
        if (radio.checked) numFaqs = parseInt(radio.value, 10);
      });

      const payload = {
        source_type: state.activeTab,
        num_faqs: numFaqs,
        difficulty: difficultySelect ? difficultySelect.value : 'Intermediate',
        answer_length: answerLengthSelect ? answerLengthSelect.value : 'Medium',
        language: languageSelect ? languageSelect.value : 'English',
        category: categorySelect ? categorySelect.value : 'General Knowledge'
      };

      // Validate based on active tab
      if (state.activeTab === 'pdf') {
        if (!state.pdfFile) {
          showToast('Please upload a PDF file before generating.', 'warning');
          return;
        }

        // If user hasn't explicitly extracted text yet, we can extract or pass file
        if (!state.extractedPdfText) {
          showLoading('Extracting PDF text...', 'Reading pages and preparing content for AI synthesis.');
          try {
            const formData = new FormData();
            formData.append('file', state.pdfFile);
            const uploadRes = await fetch('/api/upload-pdf', {
              method: 'POST',
              body: formData
            });
            const uploadData = await uploadRes.json();
            if (uploadRes.ok && uploadData.success) {
              state.extractedPdfText = uploadData.text;
            } else {
              hideLoading();
              showToast(uploadData.error || 'Failed to extract PDF text.', 'danger');
              return;
            }
          } catch (err) {
            hideLoading();
            showToast('Network error while processing PDF.', 'danger');
            return;
          }
        }
        payload.source_text = state.extractedPdfText;
        payload.source_filename = state.pdfFile.name;
      } else if (state.activeTab === 'text') {
        const textVal = textInput ? textInput.value.trim() : '';
        if (!textVal) {
          showToast('Please paste or enter some text before generating.', 'warning');
          if (textInput) textInput.focus();
          return;
        }
        if (textVal.length < 30) {
          showToast('Please provide more detailed text (at least 30 characters).', 'warning');
          return;
        }
        payload.source_text = textVal;
      } else if (state.activeTab === 'topic') {
        const topicVal = topicInput ? topicInput.value.trim() : '';
        if (!topicVal) {
          showToast('Please enter a topic or subject.', 'warning');
          if (topicInput) topicInput.focus();
          return;
        }
        const descInput = document.getElementById('topicDescription');
        const topicDesc = descInput ? descInput.value.trim() : '';
        payload.source_text = topicDesc ? `${topicVal}\n\n${topicDesc}` : topicVal;
      }

      // Trigger Generation API Call
      showLoading('Generating FAQs with AI...', 'Synthesizing key questions, explanations, and categories.');

      try {
        const response = await fetch('/api/generate', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        });

        const data = await response.json();
        hideLoading();

        if (response.ok && data.success) {
          // Construct generation object
          const aiData = data.data || {};
          const meta = data.meta || {};
          const generationResult = {
            id: null,
            title: aiData.title || 'Generated FAQs',
            source_type: meta.source_type || payload.source_type,
            source_text: payload.source_text || '',
            source_filename: meta.source_filename || payload.source_filename || null,
            difficulty: meta.difficulty || payload.difficulty,
            answer_length: meta.answer_length || payload.answer_length,
            language: meta.language || payload.language,
            category: meta.category || payload.category,
            created_at: new Date().toISOString(),
            faqs: aiData.faqs || []
          };

          // Store in sessionStorage
          sessionStorage.setItem('latestFaqGeneration', JSON.stringify(generationResult));

          // Also store original generation settings for regenerate button
          sessionStorage.setItem('lastGeneratePayload', JSON.stringify(payload));

          showToast('FAQs generated successfully! Redirecting...', 'success');

          // Navigate to results page
          setTimeout(() => {
            window.location.href = '/results/new';
          }, 400);

        } else {
          showToast(data.error || 'Failed to generate FAQs. Please try again.', 'danger');
        }
      } catch (err) {
        hideLoading();
        showToast('Network error during FAQ generation. Check your server connection.', 'danger');
      }
    });
  }

  // ==========================================
  // PAGE 2: RESULTS PAGE LOGIC
  // ==========================================

  function initResultsPage() {
    const resultsContainer = document.getElementById('faqAccordionContainer');
    if (!resultsContainer) return; // Not on results page

    // 1. Determine data source: Server template variable OR sessionStorage
    let genData = null;
    if (window.SERVER_GENERATION && window.SERVER_GENERATION.faqs) {
      genData = window.SERVER_GENERATION;
    } else {
      const stored = sessionStorage.getItem('latestFaqGeneration');
      if (stored) {
        try {
          genData = JSON.parse(stored);
        } catch (e) {
          console.error('Failed to parse sessionStorage latestFaqGeneration', e);
        }
      }
    }

    state.currentGeneration = genData;

    // If no data exists at all
    if (!genData || !genData.faqs || genData.faqs.length === 0) {
      const placeholder = document.getElementById('clientFaqPlaceholder');
      if (placeholder) {
        placeholder.innerHTML = `
          <div class="empty-state py-5">
            <div class="mb-3 text-muted"><i class="fa-solid fa-folder-open fs-1"></i></div>
            <h5 class="fw-bold text-navy">No FAQ results found</h5>
            <p class="text-muted small mb-4">No active generation was found in session or database.</p>
            <a href="/generate" class="btn btn-primary-gradient text-white rounded-pill px-4">Generate FAQs</a>
          </div>
        `;
      }
      return;
    }

    // Hydrate Header Metadata
    renderHeaderMetadata(genData);

    // If client-side rendered (sessionStorage or dynamic), render the FAQ items
    const clientAccordion = document.getElementById('faqAccordion');
    const placeholder = document.getElementById('clientFaqPlaceholder');
    if (placeholder) placeholder.classList.add('d-none');
    if (clientAccordion) clientAccordion.classList.remove('d-none');

    // Populate category filter dropdown
    populateCategoryFilter(genData.faqs);

    // If accordion is not already server-rendered, render dynamically
    if (!clientAccordion.children.length) {
      renderFaqAccordion(genData.faqs);
    }

    // Attach event listeners to all FAQ item action buttons (edit, copy, delete)
    attachFaqItemListeners();

    // 2. Expand All / Collapse All
    const btnExpandAll = document.getElementById('btnExpandAll');
    let isAllExpanded = false;
    if (btnExpandAll) {
      btnExpandAll.addEventListener('click', () => {
        const collapses = document.querySelectorAll('#faqAccordion .accordion-collapse');
        collapses.forEach(collapseEl => {
          if (window.bootstrap && window.bootstrap.Collapse) {
            const inst = bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false });
            if (!isAllExpanded) {
              inst.show();
            } else {
              inst.hide();
            }
          }
        });
        isAllExpanded = !isAllExpanded;
        btnExpandAll.innerHTML = isAllExpanded
          ? '<i class="fa-solid fa-compress me-1"></i> Collapse All'
          : '<i class="fa-solid fa-arrows-up-down me-1"></i> Expand All';
      });
    }

    // 3. Real-Time Search & Filtering
    const searchInput = document.getElementById('faqSearchInput');
    const clearSearchBtn = document.getElementById('clearFaqSearchBtn');
    const categoryFilter = document.getElementById('faqCategoryFilter');

    function applyFaqFilters() {
      const query = (searchInput ? searchInput.value.toLowerCase().trim() : '');
      const selectedCategory = (categoryFilter ? categoryFilter.value : 'all');

      if (clearSearchBtn) {
        if (query) clearSearchBtn.classList.remove('d-none');
        else clearSearchBtn.classList.add('d-none');
      }

      const items = document.querySelectorAll('#faqAccordion .faq-item-card');
      let visibleCount = 0;

      items.forEach(card => {
        const qText = card.querySelector('.faq-question-text')?.textContent.toLowerCase() || '';
        const aText = card.querySelector('.faq-answer-content')?.textContent.toLowerCase() || '';
        const cat = card.getAttribute('data-category') || '';

        const matchesQuery = !query || qText.includes(query) || aText.includes(query);
        const matchesCategory = selectedCategory === 'all' || cat.toLowerCase() === selectedCategory.toLowerCase();

        if (matchesQuery && matchesCategory) {
          card.classList.remove('d-none');
          visibleCount++;
        } else {
          card.classList.add('d-none');
        }
      });
    }

    if (searchInput) searchInput.addEventListener('input', applyFaqFilters);
    if (clearSearchBtn) {
      clearSearchBtn.addEventListener('click', () => {
        searchInput.value = '';
        applyFaqFilters();
        searchInput.focus();
      });
    }
    if (categoryFilter) categoryFilter.addEventListener('change', applyFaqFilters);

    // 4. Copy All FAQs
    const btnCopyAll = document.getElementById('btnCopyAll');
    if (btnCopyAll) {
      btnCopyAll.addEventListener('click', () => {
        if (!state.currentGeneration || !state.currentGeneration.faqs) return;
        let textBuffer = `${state.currentGeneration.title || 'FAQ Collection'}\n\n`;
        state.currentGeneration.faqs.forEach((item, index) => {
          textBuffer += `Q${index + 1}: ${item.question}\nA: ${item.answer}\n\n`;
        });
        copyToClipboard(textBuffer.trim(), 'All FAQs copied to clipboard!');
      });
    }

    // 5. Print FAQs
    const btnPrint = document.getElementById('btnPrintFaqs');
    if (btnPrint) {
      btnPrint.addEventListener('click', () => {
        window.print();
      });
    }

    // 6. Regenerate FAQs
    const btnRegenerate = document.getElementById('btnRegenerate');
    if (btnRegenerate) {
      btnRegenerate.addEventListener('click', () => {
        if (confirmAction('Regenerate FAQs using the previous settings?')) {
          const lastPayload = sessionStorage.getItem('lastGeneratePayload');
          if (lastPayload) {
            window.location.href = '/generate';
          } else {
            window.location.href = '/generate';
          }
        }
      });
    }

    // 7. Save to Database (for unsaved results)
    const btnSaveDb = document.getElementById('btnSaveToDb');
    if (btnSaveDb) {
      btnSaveDb.addEventListener('click', async () => {
        if (!state.currentGeneration) return;

        btnSaveDb.disabled = true;
        btnSaveDb.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Saving...';

        try {
          const gen = state.currentGeneration;
          const savePayload = {
            title: gen.title || 'Generated FAQs',
            source_type: gen.source_type || 'text',
            source_filename: gen.source_filename || null,
            source_text: gen.source_text || '',
            difficulty: gen.difficulty || 'intermediate',
            answer_length: gen.answer_length || 'medium',
            language: gen.language || 'English',
            category: gen.category || 'General Knowledge',
            faqs: gen.faqs || []
          };
          const response = await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(savePayload)
          });

          const data = await response.json();
          if (response.ok && data.success) {
            state.currentGeneration.id = data.generation_id;
            // Update sessionStorage
            sessionStorage.setItem('latestFaqGeneration', JSON.stringify(state.currentGeneration));

            // Replace save button with saved badge
            const saveIndicator = document.getElementById('saveStatusIndicator');
            if (saveIndicator) {
              saveIndicator.innerHTML = `
                <span class="badge bg-success-subtle text-success border border-success-subtle px-3 py-2 rounded-pill">
                  <i class="fa-solid fa-circle-check me-1"></i> Saved in Database
                </span>
              `;
            }

            // Show delete generation button now that it's saved
            const delGenBtn = document.getElementById('btnDeleteGeneration');
            if (delGenBtn) delGenBtn.classList.remove('d-none');

            showToast('Generation saved successfully to database!', 'success');
            // Redirect to the persistent results page
            setTimeout(() => {
              window.location.href = `/results/${data.generation_id}`;
            }, 600);
          } else {
            btnSaveDb.disabled = false;
            btnSaveDb.innerHTML = '<i class="fa-solid fa-floppy-disk me-1"></i> Save to Database';
            showToast(data.error || 'Failed to save generation.', 'danger');
          }
        } catch (err) {
          btnSaveDb.disabled = false;
          btnSaveDb.innerHTML = '<i class="fa-solid fa-floppy-disk me-1"></i> Save to Database';
          showToast('Network error while saving.', 'danger');
        }
      });
    }

    // 8. Title Editing (Inline)
    const btnEditTitle = document.getElementById('btnEditTitle');
    const titleDisplay = document.getElementById('titleDisplayContainer');
    const titleEdit = document.getElementById('titleEditContainer');
    const titleInput = document.getElementById('titleEditInput');
    const btnSaveTitle = document.getElementById('btnSaveTitle');
    const btnCancelTitle = document.getElementById('btnCancelTitle');
    const resultsTitle = document.getElementById('resultsTitle');

    if (btnEditTitle && titleDisplay && titleEdit) {
      btnEditTitle.addEventListener('click', () => {
        titleDisplay.classList.add('d-none');
        titleEdit.classList.remove('d-none');
        if (titleInput) {
          titleInput.value = resultsTitle.textContent.trim();
          titleInput.focus();
        }
      });

      btnCancelTitle.addEventListener('click', () => {
        titleEdit.classList.add('d-none');
        titleDisplay.classList.remove('d-none');
      });

      btnSaveTitle.addEventListener('click', async () => {
        const newTitle = titleInput.value.trim();
        if (!newTitle) {
          showToast('Title cannot be empty', 'warning');
          return;
        }

        // If saved on server, update via API
        if (state.currentGeneration && state.currentGeneration.id) {
          try {
            const res = await fetch(`/api/generation/${state.currentGeneration.id}/title`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ title: newTitle })
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
              showToast(data.error || 'Failed to update title', 'danger');
              return;
            }
          } catch (e) {
            showToast('Network error updating title', 'danger');
            return;
          }
        }

        // Update local state and DOM
        if (state.currentGeneration) state.currentGeneration.title = newTitle;
        sessionStorage.setItem('latestFaqGeneration', JSON.stringify(state.currentGeneration));
        if (resultsTitle) resultsTitle.textContent = newTitle;
        const breadcrumbTitle = document.getElementById('breadcrumbTitle');
        if (breadcrumbTitle) breadcrumbTitle.textContent = newTitle;

        titleEdit.classList.add('d-none');
        titleDisplay.classList.remove('d-none');
        showToast('Title updated', 'success');
      });
    }

    // 9. Exports Handlers
    const btnExportTxt = document.getElementById('btnExportTxt');
    const btnExportCsv = document.getElementById('btnExportCsv');
    const btnExportPdf = document.getElementById('btnExportPdf');

    if (btnExportTxt) {
      btnExportTxt.addEventListener('click', (e) => {
        e.preventDefault();
        exportFaqs('txt');
      });
    }
    if (btnExportCsv) {
      btnExportCsv.addEventListener('click', (e) => {
        e.preventDefault();
        exportFaqs('csv');
      });
    }
    if (btnExportPdf) {
      btnExportPdf.addEventListener('click', (e) => {
        e.preventDefault();
        exportFaqs('pdf');
      });
    }

    function exportFaqs(format) {
      if (!state.currentGeneration) return;

      // If saved in DB, use server route
      if (state.currentGeneration.id) {
        window.location.href = `/api/export/${state.currentGeneration.id}/${format}`;
        return;
      }

      // If unsaved in DB:
      if (format === 'txt') {
        let textContent = `${state.currentGeneration.title || 'FAQ Collection'}\n`;
        textContent += `Generated: ${new Date().toLocaleDateString()}\n`;
        textContent += `Language: ${state.currentGeneration.language || 'English'}\n\n`;
        state.currentGeneration.faqs.forEach((faq, idx) => {
          textContent += `----------------------------------------\n`;
          textContent += `Q${idx + 1}: ${faq.question}\n`;
          textContent += `Category: ${faq.category || 'General'}\n`;
          textContent += `A: ${faq.answer}\n\n`;
        });
        downloadBlob(textContent, `${sanitizeFilename(state.currentGeneration.title)}.txt`, 'text/plain');
        showToast('Exported as TXT', 'success');
      } else if (format === 'csv') {
        let csvContent = 'ID,Question,Answer,Category\n';
        state.currentGeneration.faqs.forEach((faq, idx) => {
          const q = `"${(faq.question || '').replace(/"/g, '""')}"`;
          const a = `"${(faq.answer || '').replace(/"/g, '""')}"`;
          const c = `"${(faq.category || 'General').replace(/"/g, '""')}"`;
          csvContent += `${idx + 1},${q},${a},${c}\n`;
        });
        downloadBlob(csvContent, `${sanitizeFilename(state.currentGeneration.title)}.csv`, 'text/csv');
        showToast('Exported as CSV', 'success');
      } else if (format === 'pdf') {
        showToast('Please save this generation to database first to generate a formatted PDF export.', 'warning');
      }
    }

    function sanitizeFilename(name) {
      return (name || 'faqs').replace(/[^a-z0-9_-]/gi, '_').toLowerCase();
    }

    function downloadBlob(content, filename, mimeType) {
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    // 10. Delete Generation Handler (for results page)
    const btnDeleteGen = document.getElementById('btnDeleteGeneration');
    const deleteGenModalEl = document.getElementById('deleteGenerationModal');
    const btnConfirmDeleteGen = document.getElementById('btnConfirmDeleteGen');

    if (btnDeleteGen && deleteGenModalEl) {
      btnDeleteGen.addEventListener('click', () => {
        if (window.bootstrap && window.bootstrap.Modal) {
          const modal = new bootstrap.Modal(deleteGenModalEl);
          modal.show();
        }
      });

      if (btnConfirmDeleteGen) {
        btnConfirmDeleteGen.addEventListener('click', async () => {
          if (!state.currentGeneration || !state.currentGeneration.id) return;
          try {
            const res = await fetch(`/api/generation/${state.currentGeneration.id}`, {
              method: 'DELETE'
            });
            const data = await res.json();
            if (res.ok && data.success) {
              sessionStorage.removeItem('latestFaqGeneration');
              showToast('Generation deleted', 'success');
              setTimeout(() => {
                window.location.href = '/history';
              }, 400);
            } else {
              showToast(data.error || 'Failed to delete generation', 'danger');
            }
          } catch (e) {
            showToast('Network error deleting generation', 'danger');
          }
        });
      }
    }

    // 11. Modal Setup for Edit FAQ
    initEditFaqModal();

    // 12. Modal Setup for Delete FAQ
    initDeleteFaqModal();
  }

  function renderHeaderMetadata(gen) {
    const resultsTitle = document.getElementById('resultsTitle');
    const breadcrumbTitle = document.getElementById('breadcrumbTitle');
    const badgeSourceText = document.getElementById('badgeSourceText');
    const badgeFaqCountText = document.getElementById('badgeFaqCountText');
    const badgeDifficultyText = document.getElementById('badgeDifficultyText');
    const badgeLanguageText = document.getElementById('badgeLanguageText');
    const badgeAnswerLengthText = document.getElementById('badgeAnswerLengthText');
    const resultsDateText = document.getElementById('resultsDateText');

    if (resultsTitle && gen.title) resultsTitle.textContent = gen.title;
    if (breadcrumbTitle && gen.title) breadcrumbTitle.textContent = gen.title;
    if (badgeSourceText && gen.source_type) badgeSourceText.textContent = gen.source_type.toUpperCase();
    if (badgeFaqCountText && gen.faqs) badgeFaqCountText.textContent = `${gen.faqs.length} FAQs`;
    if (badgeDifficultyText && gen.difficulty) badgeDifficultyText.textContent = gen.difficulty;
    if (badgeLanguageText && gen.language) badgeLanguageText.textContent = gen.language;
    if (badgeAnswerLengthText && gen.answer_length) badgeAnswerLengthText.textContent = gen.answer_length;
    if (resultsDateText && gen.created_at) resultsDateText.textContent = formatDate(gen.created_at);
  }

  function populateCategoryFilter(faqs) {
    const filter = document.getElementById('faqCategoryFilter');
    if (!filter || !faqs) return;

    const categories = new Set();
    faqs.forEach(f => {
      if (f.category) categories.add(f.category);
    });

    filter.innerHTML = '<option value="all" selected>All Categories</option>';
    categories.forEach(cat => {
      const opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = cat;
      filter.appendChild(opt);
    });
  }

  function renderFaqAccordion(faqs) {
    const container = document.getElementById('faqAccordion');
    if (!container) return;
    container.innerHTML = '';

    faqs.forEach((faq, index) => {
      const itemEl = document.createElement('div');
      itemEl.className = 'accordion-item faq-item-card border-0 mb-3 shadow-sm rounded-12 overflow-hidden';
      itemEl.setAttribute('data-faq-id', faq.id || (index + 1));
      itemEl.setAttribute('data-index', index);
      itemEl.setAttribute('data-category', faq.category || 'General');

      itemEl.innerHTML = `
        <h2 class="accordion-header" id="heading-${index + 1}">
          <button class="accordion-button collapsed px-4 py-3 bg-white" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${index + 1}" aria-expanded="false" aria-controls="collapse-${index + 1}">
            <span class="faq-number-badge me-3">Q${index + 1}</span>
            <span class="faq-question-text fw-semibold text-navy flex-grow-1 me-2">${escapeHtml(faq.question)}</span>
            <span class="badge bg-light text-secondary border me-3 d-none d-sm-inline-block faq-category-tag">
              ${escapeHtml(faq.category || 'General')}
            </span>
          </button>
        </h2>
        <div id="collapse-${index + 1}" class="accordion-collapse collapse" aria-labelledby="heading-${index + 1}" data-bs-parent="#faqAccordion">
          <div class="accordion-body px-4 pb-4 pt-2 bg-white">
            <div class="faq-answer-content text-dark mb-3">${escapeHtml(faq.answer)}</div>
            <div class="d-flex align-items-center justify-content-between pt-2 border-top border-light-subtle flex-wrap gap-2">
              <div class="d-sm-none">
                <span class="badge bg-light text-secondary border">${escapeHtml(faq.category || 'General')}</span>
              </div>
              <div class="ms-auto d-flex align-items-center gap-2">
                <button type="button" class="btn btn-sm btn-link text-muted text-decoration-none btn-copy-faq" title="Copy Question and Answer">
                  <i class="fa-regular fa-copy me-1"></i> Copy
                </button>
                <button type="button" class="btn btn-sm btn-link text-primary text-decoration-none btn-edit-faq" title="Edit Question or Answer">
                  <i class="fa-solid fa-pen me-1"></i> Edit
                </button>
                <button type="button" class="btn btn-sm btn-link text-danger text-decoration-none btn-delete-faq" title="Delete this FAQ">
                  <i class="fa-regular fa-trash-can me-1"></i> Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
      container.appendChild(itemEl);
    });
  }

  function attachFaqItemListeners() {
    // 1. Copy FAQ item
    document.querySelectorAll('.btn-copy-faq').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = btn.closest('.faq-item-card');
        if (!card) return;
        const q = card.querySelector('.faq-question-text')?.textContent.trim() || '';
        const a = card.querySelector('.faq-answer-content')?.textContent.trim() || '';
        copyToClipboard(`Q: ${q}\nA: ${a}`, 'FAQ copied to clipboard!');
      });
    });

    // 2. Edit FAQ item (opens modal)
    document.querySelectorAll('.btn-edit-faq').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = btn.closest('.faq-item-card');
        if (!card) return;
        const faqId = card.getAttribute('data-faq-id');
        const index = card.getAttribute('data-index');
        const q = card.querySelector('.faq-question-text')?.textContent.trim() || '';
        const a = card.querySelector('.faq-answer-content')?.textContent.trim() || '';
        const c = card.getAttribute('data-category') || 'General';

        const idInput = document.getElementById('editModalFaqId');
        const indexInput = document.getElementById('editModalItemIndex');
        const qInput = document.getElementById('editModalQuestion');
        const aInput = document.getElementById('editModalAnswer');
        const cInput = document.getElementById('editModalCategory');

        if (idInput) idInput.value = faqId;
        if (indexInput) indexInput.value = index !== null ? index : '';
        if (qInput) qInput.value = q;
        if (aInput) aInput.value = a;
        if (cInput) cInput.value = c;

        const modalEl = document.getElementById('editFaqModal');
        if (modalEl && window.bootstrap && window.bootstrap.Modal) {
          const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
          modal.show();
        }
      });
    });

    // 3. Delete FAQ item (opens modal)
    document.querySelectorAll('.btn-delete-faq').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = btn.closest('.faq-item-card');
        if (!card) return;
        const faqId = card.getAttribute('data-faq-id');
        const index = card.getAttribute('data-index');

        const delIdInput = document.getElementById('deleteModalFaqId');
        const delIdxInput = document.getElementById('deleteModalIndex');
        if (delIdInput) delIdInput.value = faqId;
        if (delIdxInput) delIdxInput.value = index !== null ? index : '';

        const modalEl = document.getElementById('deleteFaqModal');
        if (modalEl && window.bootstrap && window.bootstrap.Modal) {
          const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
          modal.show();
        }
      });
    });
  }

  function initEditFaqModal() {
    const saveBtn = document.getElementById('btnSaveFaqEdit');
    const modalEl = document.getElementById('editFaqModal');
    if (!saveBtn || !modalEl) return;

    saveBtn.addEventListener('click', async () => {
      const faqId = document.getElementById('editModalFaqId')?.value;
      const indexStr = document.getElementById('editModalItemIndex')?.value;
      const question = document.getElementById('editModalQuestion')?.value.trim();
      const answer = document.getElementById('editModalAnswer')?.value.trim();
      const category = document.getElementById('editModalCategory')?.value.trim() || 'General';

      if (!question || !answer) {
        showToast('Question and Answer cannot be empty.', 'warning');
        return;
      }

      // If item has a persistent database ID (numeric)
      if (faqId && !isNaN(parseInt(faqId, 10)) && state.currentGeneration && state.currentGeneration.id) {
        try {
          const res = await fetch(`/api/faq/${faqId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, answer, category })
          });
          const data = await res.json();
          if (!res.ok || !data.success) {
            showToast(data.error || 'Failed to update FAQ on server', 'danger');
            return;
          }
        } catch (e) {
          showToast('Network error while saving FAQ update', 'danger');
          return;
        }
      }

      // Update in DOM
      const card = document.querySelector(`.faq-item-card[data-faq-id="${faqId}"]`);
      if (card) {
        const qEl = card.querySelector('.faq-question-text');
        const aEl = card.querySelector('.faq-answer-content');
        const cBadge = card.querySelector('.faq-category-tag');
        if (qEl) qEl.textContent = question;
        if (aEl) aEl.textContent = answer;
        if (cBadge) cBadge.textContent = category;
        card.setAttribute('data-category', category);
      }

      // Update in local state
      if (state.currentGeneration && state.currentGeneration.faqs) {
        const idx = indexStr !== '' ? parseInt(indexStr, 10) : -1;
        if (idx >= 0 && idx < state.currentGeneration.faqs.length) {
          state.currentGeneration.faqs[idx].question = question;
          state.currentGeneration.faqs[idx].answer = answer;
          state.currentGeneration.faqs[idx].category = category;
        }
        sessionStorage.setItem('latestFaqGeneration', JSON.stringify(state.currentGeneration));
      }

      if (window.bootstrap && window.bootstrap.Modal) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
      }

      showToast('FAQ updated successfully', 'success');
    });
  }

  function initDeleteFaqModal() {
    const confirmBtn = document.getElementById('btnConfirmDeleteFaq');
    const modalEl = document.getElementById('deleteFaqModal');
    if (!confirmBtn || !modalEl) return;

    confirmBtn.addEventListener('click', async () => {
      const faqId = document.getElementById('deleteModalFaqId')?.value;
      const indexStr = document.getElementById('deleteModalIndex')?.value;

      // If persistent on server
      if (faqId && !isNaN(parseInt(faqId, 10)) && state.currentGeneration && state.currentGeneration.id) {
        try {
          const res = await fetch(`/api/faq/${faqId}`, {
            method: 'DELETE'
          });
          const data = await res.json();
          if (!res.ok || !data.success) {
            showToast(data.error || 'Failed to delete FAQ from server', 'danger');
            return;
          }
        } catch (e) {
          showToast('Network error while deleting FAQ', 'danger');
          return;
        }
      }

      // Remove from DOM
      const card = document.querySelector(`.faq-item-card[data-faq-id="${faqId}"]`);
      if (card) card.remove();

      // Remove from state
      if (state.currentGeneration && state.currentGeneration.faqs) {
        const idx = indexStr !== '' ? parseInt(indexStr, 10) : -1;
        if (idx >= 0 && idx < state.currentGeneration.faqs.length) {
          state.currentGeneration.faqs.splice(idx, 1);
        }
        sessionStorage.setItem('latestFaqGeneration', JSON.stringify(state.currentGeneration));

        // Update count badge
        const badgeCount = document.getElementById('badgeFaqCountText');
        if (badgeCount) badgeCount.textContent = `${state.currentGeneration.faqs.length} FAQs`;
      }

      if (window.bootstrap && window.bootstrap.Modal) {
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
      }

      showToast('FAQ deleted', 'info');
    });
  }

  // ==========================================
  // PAGE 3: HISTORY PAGE LOGIC
  // ==========================================

  function initHistoryPage() {
    const historyContainer = document.getElementById('historyItemsContainer');
    if (!historyContainer) return; // Not on history page

    // 1. Search and source filter
    const searchInput = document.getElementById('historySearchInput');
    const clearSearchBtn = document.getElementById('clearHistorySearchBtn');
    const filterButtons = document.querySelectorAll('.history-filter-btn');
    const noResultsMsg = document.getElementById('noSearchResultsMsg');
    const resetSearchBtn = document.getElementById('resetHistorySearchBtn');

    let currentSourceFilter = 'all';

    function filterHistory() {
      const query = (searchInput ? searchInput.value.toLowerCase().trim() : '');

      if (clearSearchBtn) {
        if (query) clearSearchBtn.classList.remove('d-none');
        else clearSearchBtn.classList.add('d-none');
      }

      const items = document.querySelectorAll('.history-item-card');
      let visibleCount = 0;

      items.forEach(card => {
        const title = card.getAttribute('data-title') || '';
        const source = card.getAttribute('data-source') || '';

        const matchesQuery = !query || title.includes(query) || source.includes(query);
        const matchesSource = currentSourceFilter === 'all' || source === currentSourceFilter;

        if (matchesQuery && matchesSource) {
          card.classList.remove('d-none');
          visibleCount++;
        } else {
          card.classList.add('d-none');
        }
      });

      if (noResultsMsg) {
        if (visibleCount === 0 && items.length > 0) {
          noResultsMsg.classList.remove('d-none');
        } else {
          noResultsMsg.classList.add('d-none');
        }
      }
    }

    if (searchInput) searchInput.addEventListener('input', filterHistory);
    if (clearSearchBtn) {
      clearSearchBtn.addEventListener('click', () => {
        searchInput.value = '';
        filterHistory();
        searchInput.focus();
      });
    }

    if (resetSearchBtn) {
      resetSearchBtn.addEventListener('click', () => {
        if (searchInput) searchInput.value = '';
        currentSourceFilter = 'all';
        filterButtons.forEach(b => {
          b.classList.toggle('active', b.getAttribute('data-filter') === 'all');
        });
        filterHistory();
      });
    }

    filterButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        filterButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentSourceFilter = btn.getAttribute('data-filter') || 'all';
        filterHistory();
      });
    });

    // 2. Rename Generation Modal
    const renameModalEl = document.getElementById('renameGenerationModal');
    const renameInput = document.getElementById('renameGenInput');
    const renameIdInput = document.getElementById('renameGenId');
    const btnConfirmRename = document.getElementById('btnConfirmRenameGen');

    document.querySelectorAll('.btn-history-rename').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        const title = btn.getAttribute('data-title');
        if (renameIdInput) renameIdInput.value = id;
        if (renameInput) {
          renameInput.value = title;
          setTimeout(() => renameInput.focus(), 300);
        }
        if (renameModalEl && window.bootstrap && window.bootstrap.Modal) {
          const modal = bootstrap.Modal.getOrCreateInstance(renameModalEl);
          modal.show();
        }
      });
    });

    if (btnConfirmRename) {
      btnConfirmRename.addEventListener('click', async () => {
        const id = renameIdInput.value;
        const newTitle = renameInput.value.trim();
        if (!newTitle) {
          showToast('Title cannot be empty', 'warning');
          return;
        }

        try {
          const res = await fetch(`/api/generation/${id}/title`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
          });
          const data = await res.json();
          if (res.ok && data.success) {
            // Update in DOM
            const card = document.querySelector(`.history-item-card[data-id="${id}"]`);
            if (card) {
              const titleEl = card.querySelector('.item-title-text');
              if (titleEl) titleEl.textContent = newTitle;
              card.setAttribute('data-title', newTitle.toLowerCase());
              const renameBtn = card.querySelector('.btn-history-rename');
              if (renameBtn) renameBtn.setAttribute('data-title', newTitle);
            }

            if (window.bootstrap && window.bootstrap.Modal) {
              const modal = bootstrap.Modal.getInstance(renameModalEl);
              if (modal) modal.hide();
            }
            showToast('Title updated successfully', 'success');
          } else {
            showToast(data.error || 'Failed to update title', 'danger');
          }
        } catch (e) {
          showToast('Network error updating title', 'danger');
        }
      });
    }

    // 3. Delete Generation Modal
    const deleteModalEl = document.getElementById('deleteHistoryModal');
    const deleteIdInput = document.getElementById('deleteHistoryGenId');
    const deletePrompt = document.getElementById('deleteHistoryPromptText');
    const btnConfirmDelete = document.getElementById('btnConfirmDeleteHistory');

    document.querySelectorAll('.btn-history-delete').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        const title = btn.getAttribute('data-title') || 'this FAQ collection';
        if (deleteIdInput) deleteIdInput.value = id;
        if (deletePrompt) deletePrompt.textContent = `Are you sure you want to permanently delete "${title}"?`;

        if (deleteModalEl && window.bootstrap && window.bootstrap.Modal) {
          const modal = bootstrap.Modal.getOrCreateInstance(deleteModalEl);
          modal.show();
        }
      });
    });

    if (btnConfirmDelete) {
      btnConfirmDelete.addEventListener('click', async () => {
        const id = deleteIdInput.value;
        if (!id) return;

        try {
          const res = await fetch(`/api/generation/${id}`, {
            method: 'DELETE'
          });
          const data = await res.json();
          if (res.ok && data.success) {
            const card = document.querySelector(`.history-item-card[data-id="${id}"]`);
            if (card) card.remove();

            if (window.bootstrap && window.bootstrap.Modal) {
              const modal = bootstrap.Modal.getInstance(deleteModalEl);
              if (modal) modal.hide();
            }
            showToast('Generation deleted', 'success');

            // If no items left, reload to show empty state
            const remaining = document.querySelectorAll('.history-item-card');
            if (remaining.length === 0) {
              window.location.reload();
            }
          } else {
            showToast(data.error || 'Failed to delete generation', 'danger');
          }
        } catch (e) {
          showToast('Network error deleting generation', 'danger');
        }
      });
    }
  }

  // ==========================================
  // INITIALIZATION ON DOMContentLoaded
  // ==========================================

  document.addEventListener('DOMContentLoaded', () => {
    // Prevent accidental standard form submits
    document.querySelectorAll('form').forEach(form => {
      form.addEventListener('submit', (e) => {
        if (!form.getAttribute('action')) {
          e.preventDefault();
        }
      });
    });

    // Initialize specific page controllers
    initGeneratePage();
    initResultsPage();
    initHistoryPage();
  });

  // Expose helpful globals for inline debugging or extensions
  window.AIFaqApp = {
    showToast,
    formatDate,
    formatFileSize,
    showLoading,
    hideLoading,
    copyToClipboard,
    state
  };

})();
