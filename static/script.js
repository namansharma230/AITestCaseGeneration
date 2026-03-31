/* ═══════════════════════════════════════════════════════════════════════════
   Test Case Automator — Dashboard Script
   Handles form submission, SSE log streaming, and UI state management
   ═══════════════════════════════════════════════════════════════════════════ */

(() => {
    'use strict';

    // ── DOM References ───────────────────────────────────────────────────────
    const form        = document.getElementById('generate-form');
    const urlInput    = document.getElementById('url-input');
    const submitBtn   = document.getElementById('submit-btn');

    const confluenceForm   = document.getElementById('confluence-form');
    const confluenceUrlInput = document.getElementById('confluence-url-input');
    const confluenceSubmitBtn = document.getElementById('confluence-submit-btn');

    const logBody     = document.getElementById('log-body');
    const logPlaceholder = document.getElementById('log-placeholder');

    const statusBanner    = document.getElementById('status-banner');
    const statusIcon      = document.getElementById('status-icon');
    const statusText      = document.getElementById('status-text');
    const progressSteps   = document.getElementById('progress-steps');
    const celebration     = document.getElementById('celebration');

    const statUrl         = document.getElementById('stat-url');
    const statTestCases   = document.getElementById('stat-test-cases');
    const statStatus      = document.getElementById('stat-status');

    const resultsPanel    = document.getElementById('results-panel');
    const resultsSubtitle = document.getElementById('results-subtitle');
    const downloadBtn     = document.getElementById('download-btn');
    const errorHint       = document.getElementById('error-hint');

    let currentEventSource = null;
    let currentStepIndex   = -1;

    // ── Download Button ──────────────────────────────────────────────────────
    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
            window.location.href = '/api/download';
        });
    }

    // ── Jira Form Submission ─────────────────────────────────────────────────
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const url = urlInput.value.trim();

        if (!url) return;

        // Reset UI
        resetUI();
        setAllFormsLoading(true);
        showBanner('processing', '⚡', 'Starting Jira test case generation...');
        showProgressSteps();

        // Update stats
        statUrl.textContent     = truncateUrl(url);
        statTestCases.textContent = '—';
        statStatus.textContent  = 'Running';

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url }),
            });

            const data = await res.json();

            if (!res.ok) {
                showBanner('error', '❌', data.error || 'Request failed.');
                setAllFormsLoading(false);
                statStatus.textContent = 'Error';
                return;
            }

            // Subscribe to SSE log stream
            subscribeToLogs(data.job_id);

        } catch (err) {
            showBanner('error', '❌', `Network error: ${err.message}`);
            setAllFormsLoading(false);
            statStatus.textContent = 'Error';
        }
    });

    // ── Confluence Form Submission ────────────────────────────────────────────
    confluenceForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const confluenceUrl = confluenceUrlInput.value.trim();
        if (!confluenceUrl) return;

        // Reset UI
        resetUI();
        setAllFormsLoading(true);
        showBanner('processing', '⚡', 'Starting Confluence test case generation...');
        showProgressSteps();

        // Update stats
        statUrl.textContent     = truncateUrl(confluenceUrl);
        statTestCases.textContent = '—';
        statStatus.textContent  = 'Running';

        try {
            const res = await fetch('/api/generate-confluence', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confluence_url: confluenceUrl }),
            });

            const data = await res.json();

            if (!res.ok) {
                showBanner('error', '❌', data.error || 'Request failed.');
                setAllFormsLoading(false);
                statStatus.textContent = 'Error';
                return;
            }

            // Subscribe to SSE log stream
            subscribeToLogs(data.job_id);

        } catch (err) {
            showBanner('error', '❌', `Network error: ${err.message}`);
            setAllFormsLoading(false);
            statStatus.textContent = 'Error';
        }
    });

    // ── SSE Log Streaming ────────────────────────────────────────────────────
    function subscribeToLogs(jobId) {
        // Close any existing connection
        if (currentEventSource) {
            currentEventSource.close();
            currentEventSource = null;
        }

        const es = new EventSource(`/api/logs/${jobId}`);
        currentEventSource = es;

        es.onmessage = (event) => {
            try {
                const item = JSON.parse(event.data);
                handleLogItem(item);
            } catch (err) {
                console.error('Failed to parse SSE data:', err);
            }
        };

        es.onerror = () => {
            es.close();
            currentEventSource = null;
        };
    }

    function handleLogItem(item) {
        switch (item.type) {
            case 'log':
                appendLog(item.data, item.level);
                break;

            case 'step':
                appendLog(item.data, 'step');
                advanceProgressStep();
                break;

            case 'done':
                // Stream ended — final status
                break;

            case 'summary':
                handleCompletion(item);
                break;
        }
    }

    // ── Log Panel ────────────────────────────────────────────────────────────
    function appendLog(text, level) {
        // Hide placeholder
        if (logPlaceholder) logPlaceholder.style.display = 'none';

        const line = document.createElement('div');
        line.className = `log-line log-line--${level || 'INFO'}`;

        // Highlight log level in brackets
        const highlighted = text.replace(
            /\[(INFO|WARNING|ERROR|DEBUG)\]/,
            (match, lvl) => `<span class="log-level">[${lvl}]</span>`
        );
        line.innerHTML = highlighted;

        logBody.appendChild(line);

        // Auto-scroll to bottom
        logBody.scrollTop = logBody.scrollHeight;
    }

    // ── Progress Steps ───────────────────────────────────────────────────────
    function showProgressSteps() {
        progressSteps.classList.add('progress-steps--visible');
        currentStepIndex = -1;
        document.querySelectorAll('.progress-step').forEach(s => {
            s.classList.remove('progress-step--active', 'progress-step--done');
        });
    }

    function advanceProgressStep() {
        const steps = document.querySelectorAll('.progress-step');

        // Mark current step as done
        if (currentStepIndex >= 0 && currentStepIndex < steps.length) {
            steps[currentStepIndex].classList.remove('progress-step--active');
            steps[currentStepIndex].classList.add('progress-step--done');
            const icon = steps[currentStepIndex].querySelector('.progress-step__icon');
            if (icon) icon.textContent = '✓';
        }

        // Advance to next step
        currentStepIndex++;
        if (currentStepIndex < steps.length) {
            steps[currentStepIndex].classList.add('progress-step--active');
        }
    }

    // ── Completion Handler ───────────────────────────────────────────────────
    function handleCompletion(summary) {
        setAllFormsLoading(false);

        if (currentEventSource) {
            currentEventSource.close();
            currentEventSource = null;
        }

        // Mark all remaining steps as done
        document.querySelectorAll('.progress-step').forEach(s => {
            s.classList.remove('progress-step--active');
            s.classList.add('progress-step--done');
            const icon = s.querySelector('.progress-step__icon');
            if (icon) icon.textContent = '✓';
        });

        if (summary.status === 'success') {
            showBanner('success', '🎉', summary.message);
            statTestCases.textContent = summary.test_count;
            statStatus.textContent = 'Complete';
            // Show results panel with download button
            if (resultsSubtitle) {
                resultsSubtitle.textContent = `${summary.test_count} test case(s) generated and saved to Documents\\TestCaseAutomator\\test_cases.xlsx`;
            }
            if (resultsPanel) resultsPanel.style.display = 'flex';
            if (errorHint) errorHint.style.display = 'none';
            triggerCelebration();
        } else {
            showBanner('error', '❌', summary.message || 'An error occurred.');
            statStatus.textContent = 'Failed';
            // Show troubleshooting hints
            if (errorHint) errorHint.style.display = 'block';
            if (resultsPanel) resultsPanel.style.display = 'none';
        }
    }

    // ── Status Banner ────────────────────────────────────────────────────────
    function showBanner(type, icon, message) {
        statusBanner.className = `status-banner status-banner--visible status-banner--${type}`;
        statusIcon.textContent = icon;
        statusText.textContent = message;
    }

    function hideBanner() {
        statusBanner.className = 'status-banner';
    }

    // ── Form State ───────────────────────────────────────────────────────────
    function setAllFormsLoading(loading) {
        // Jira form
        urlInput.disabled      = loading;
        submitBtn.disabled     = loading;

        // Confluence form
        confluenceUrlInput.disabled  = loading;
        confluenceSubmitBtn.disabled = loading;

        if (loading) {
            submitBtn.classList.add('btn--loading');
            confluenceSubmitBtn.classList.add('btn--loading');
        } else {
            submitBtn.classList.remove('btn--loading');
            confluenceSubmitBtn.classList.remove('btn--loading');
        }
    }

    // ── Reset UI ─────────────────────────────────────────────────────────────
    function resetUI() {
        // Clear logs
        logBody.innerHTML = '';
        if (logPlaceholder) {
            logBody.appendChild(logPlaceholder);
            logPlaceholder.style.display = 'block';
        }

        // Hide banners
        hideBanner();

        // Reset progress
        progressSteps.classList.remove('progress-steps--visible');
        currentStepIndex = -1;

        // Hide celebration
        celebration.classList.remove('celebration--active');
        celebration.innerHTML = '';

        // Hide results panel & error hint
        if (resultsPanel) resultsPanel.style.display = 'none';
        if (errorHint) errorHint.style.display = 'none';

        // Close existing SSE
        if (currentEventSource) {
            currentEventSource.close();
            currentEventSource = null;
        }
    }

    // ── Confetti Celebration ─────────────────────────────────────────────────
    function triggerCelebration() {
        celebration.innerHTML = '';
        celebration.classList.add('celebration--active');

        const colors = ['#06b6d4', '#8b5cf6', '#10b981', '#f59e0b', '#6366f1', '#ec4899', '#fff'];

        for (let i = 0; i < 80; i++) {
            const confetti = document.createElement('div');
            confetti.className = 'confetti';
            confetti.style.left         = Math.random() * 100 + '%';
            confetti.style.background   = colors[Math.floor(Math.random() * colors.length)];
            confetti.style.animationDelay    = Math.random() * 1.5 + 's';
            confetti.style.animationDuration = (2 + Math.random() * 2) + 's';
            confetti.style.width  = (4 + Math.random() * 8) + 'px';
            confetti.style.height = (4 + Math.random() * 8) + 'px';
            celebration.appendChild(confetti);
        }

        // Remove after animation
        setTimeout(() => {
            celebration.classList.remove('celebration--active');
            celebration.innerHTML = '';
        }, 5000);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    function truncateUrl(url) {
        try {
            const u = new URL(url);
            const path = u.pathname;
            if (path.length > 30) {
                return u.hostname + '/...' + path.slice(-20);
            }
            return u.hostname + path;
        } catch {
            return url.length > 40 ? url.slice(0, 40) + '...' : url;
        }
    }
})();
