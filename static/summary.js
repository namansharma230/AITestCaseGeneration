/**
 * summary.js
 * Handles the Summary & Dependencies page:
 * - Auto-detects Jira vs Confluence URL (hides selector for Confluence)
 * - Submits to /api/summarize, subscribes to SSE logs
 * - On completion, fetches /api/result/<job_id> and renders summary + deps table
 */
(() => {
    'use strict';

    // ── DOM References ───────────────────────────────────────────────────────
    const form            = document.getElementById('summary-form');
    const urlInput        = document.getElementById('summary-url-input');
    const submitBtn       = document.getElementById('summary-submit-btn');

    const confluenceForm        = document.getElementById('summary-confluence-form');
    const confluenceUrlInput    = document.getElementById('summary-confluence-url-input');
    const confluenceSubmitBtn   = document.getElementById('summary-confluence-submit-btn');

    const logBody         = document.getElementById('log-body');
    const logPlaceholder  = document.getElementById('log-placeholder');

    const statusBanner    = document.getElementById('status-banner');
    const statusIcon      = document.getElementById('status-icon');
    const statusText      = document.getElementById('status-text');
    const progressSteps   = document.getElementById('progress-steps');

    const resultsSection  = document.getElementById('results-section');
    const summaryOverview = document.getElementById('summary-overview');
    const summaryFeatures = document.getElementById('summary-features');
    const summaryScope    = document.getElementById('summary-scope');
    const complexityBadge = document.getElementById('complexity-badge');

    const depsTbody       = document.getElementById('deps-tbody');
    const depsCountBadge  = document.getElementById('deps-count-badge');
    const depsEmpty       = document.getElementById('deps-empty');

    const resultsPanel        = document.getElementById('results-panel');
    const resultsSubtitle     = document.getElementById('results-subtitle');
    const downloadSummaryBtn  = document.getElementById('download-summary-btn');
    const errorHint           = document.getElementById('error-hint');

    let currentEventSource = null;
    let currentStepIndex   = -1;
    let currentJobId       = null;

    // ── Download Button ──────────────────────────────────────────────────────
    if (downloadSummaryBtn) {
        downloadSummaryBtn.addEventListener('click', () => {
            window.location.href = '/api/download-summary';
        });
    }

    // ── Form Submissions ─────────────────────────────────────────────────────
    if (form) {
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            handleSubmission({
                url: urlInput.value.trim(),
                isConfluence: false
            });
        });
    }

    if (confluenceForm) {
        confluenceForm.addEventListener('submit', (e) => {
            e.preventDefault();
            handleSubmission({
                url: confluenceUrlInput.value.trim(),
                selector: null,
                isConfluence: true
            });
        });
    }

    async function handleSubmission({ url, isConfluence }) {
        if (!url) return;

        resetUI();
        setFormLoading(true, isConfluence);
        showBanner('processing', '⚡', 'Starting requirement analysis...');
        showProgressSteps();

        try {
            const body = { url };
            // No selector sent — the backend defaults to JIRA_CSS_SELECTOR from config.py

            const res = await fetch('/api/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });

            const data = await res.json();

            if (!res.ok) {
                showBanner('error', '❌', data.error || 'Request failed.');
                setFormLoading(false, isConfluence);
                return;
            }

            currentJobId = data.job_id;
            // Pass isConfluence to completion handler via a global or closure
            subscribeToLogs(data.job_id, isConfluence);

        } catch (err) {
            showBanner('error', '❌', `Network error: ${err.message}`);
            setFormLoading(false, isConfluence);
        }
    }

    // ── SSE Log Streaming ────────────────────────────────────────────────────
    function subscribeToLogs(jobId, isConfluence) {
        if (currentEventSource) {
            currentEventSource.close();
            currentEventSource = null;
        }

        const es = new EventSource(`/api/logs/${jobId}`);
        currentEventSource = es;

        es.onmessage = (event) => {
            try {
                const item = JSON.parse(event.data);
                handleLogItem(item, isConfluence);
            } catch (err) {
                console.error('Failed to parse SSE data:', err);
            }
        };

        es.onerror = () => {
            es.close();
            currentEventSource = null;
        };
    }

    function handleLogItem(item, isConfluence) {
        switch (item.type) {
            case 'log':
                appendLog(item.data, item.level);
                break;
            case 'step':
                appendLog(item.data, 'step');
                advanceProgressStep();
                break;
            case 'done':
                break;
            case 'summary':
                handleCompletion(item, isConfluence);
                break;
        }
    }

    // ── Log Panel ────────────────────────────────────────────────────────────
    function appendLog(text, level) {
        if (logPlaceholder) logPlaceholder.style.display = 'none';

        const line = document.createElement('div');
        line.className = `log-line log-line--${level || 'INFO'}`;

        const highlighted = text.replace(
            /\[(INFO|WARNING|ERROR|DEBUG)\]/,
            (match, lvl) => `<span class="log-level">[${lvl}]</span>`
        );
        line.innerHTML = highlighted;
        logBody.appendChild(line);
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
        if (currentStepIndex >= 0 && currentStepIndex < steps.length) {
            steps[currentStepIndex].classList.remove('progress-step--active');
            steps[currentStepIndex].classList.add('progress-step--done');
            const icon = steps[currentStepIndex].querySelector('.progress-step__icon');
            if (icon) icon.textContent = '✓';
        }
        currentStepIndex++;
        if (currentStepIndex < steps.length) {
            steps[currentStepIndex].classList.add('progress-step--active');
        }
    }

    // ── Completion Handler ───────────────────────────────────────────────────
    async function handleCompletion(summaryMsg, isConfluence) {
        setFormLoading(false, isConfluence);

        if (currentEventSource) {
            currentEventSource.close();
            currentEventSource = null;
        }

        document.querySelectorAll('.progress-step').forEach(s => {
            s.classList.remove('progress-step--active');
            s.classList.add('progress-step--done');
            const icon = s.querySelector('.progress-step__icon');
            if (icon) icon.textContent = '✓';
        });

        if (summaryMsg.status === 'success') {
            showBanner('success', '🎉', summaryMsg.message || 'Analysis complete!');
            // Show results panel with download button
            if (resultsSubtitle) {
                resultsSubtitle.textContent = 'Summary and dependencies saved to Documents\\TestCaseAutomator\\summary_requirements.xlsx';
            }
            if (resultsPanel) resultsPanel.style.display = 'flex';
            if (errorHint) errorHint.style.display = 'none';
            // Fetch the actual result data
            await fetchAndRenderResults(currentJobId);
        } else {
            showBanner('error', '❌', summaryMsg.message || 'An error occurred.');
            // Show troubleshooting hints
            if (errorHint) errorHint.style.display = 'block';
            if (resultsPanel) resultsPanel.style.display = 'none';
        }
    }

    // ── Fetch & Render Results ───────────────────────────────────────────────
    async function fetchAndRenderResults(jobId) {
        try {
            const res = await fetch(`/api/result/${jobId}`);
            const data = await res.json();

            if (data.status !== 'success' || !data.result) {
                showBanner('error', '❌', 'Failed to load results.');
                return;
            }

            renderSummary(data.result.summary);
            renderDependencies(data.result.dependencies);
            resultsSection.style.display = 'block';

            // Smooth scroll to results
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

        } catch (err) {
            console.error('Failed to fetch results:', err);
            showBanner('error', '❌', 'Failed to load results.');
        }
    }

    function renderSummary(summary) {
        if (!summary) return;

        summaryOverview.textContent = summary.overview || 'No overview available.';

        // Key features
        summaryFeatures.innerHTML = '';
        (summary.key_features || []).forEach(feat => {
            const li = document.createElement('li');
            li.textContent = feat;
            summaryFeatures.appendChild(li);
        });

        summaryScope.textContent = summary.scope || 'Not specified.';

        // Complexity badge
        const complexity = summary.complexity || 'Unknown';
        complexityBadge.textContent = complexity;
        complexityBadge.className = 'card__title-badge';
        if (complexity.toLowerCase() === 'high') {
            complexityBadge.classList.add('badge--high');
        } else if (complexity.toLowerCase() === 'medium') {
            complexityBadge.classList.add('badge--medium');
        } else if (complexity.toLowerCase() === 'low') {
            complexityBadge.classList.add('badge--low');
        }
    }

    function renderDependencies(deps) {
        depsTbody.innerHTML = '';

        if (!deps || deps.length === 0) {
            depsEmpty.style.display = 'block';
            depsCountBadge.textContent = '0 deps';
            return;
        }

        depsEmpty.style.display = 'none';
        depsCountBadge.textContent = `${deps.length} dep${deps.length !== 1 ? 's' : ''}`;

        deps.forEach(dep => {
            const tr = document.createElement('tr');

            // Category cell with badge
            const catTd = document.createElement('td');
            const catBadge = document.createElement('span');
            catBadge.className = `deps-category deps-category--${(dep.category || 'other').toLowerCase().replace(/[^a-z]/g, '')}`;
            catBadge.textContent = dep.category || 'Other';
            catTd.appendChild(catBadge);
            tr.appendChild(catTd);

            // Item cell
            const itemTd = document.createElement('td');
            itemTd.className = 'deps-item';
            itemTd.textContent = dep.item || '';
            tr.appendChild(itemTd);

            // Description cell
            const descTd = document.createElement('td');
            descTd.textContent = dep.description || '';
            tr.appendChild(descTd);

            // Owner cell
            const ownerTd = document.createElement('td');
            const ownerBadge = document.createElement('span');
            ownerBadge.className = `deps-owner deps-owner--${(dep.owner || 'other').toLowerCase().replace(/[^a-z]/g, '')}`;
            ownerBadge.textContent = dep.owner || 'Unknown';
            ownerTd.appendChild(ownerBadge);
            tr.appendChild(ownerTd);

            // Priority cell
            const prioTd = document.createElement('td');
            const prioBadge = document.createElement('span');
            prioBadge.className = `deps-priority deps-priority--${(dep.priority || 'medium').toLowerCase()}`;
            prioBadge.textContent = dep.priority || 'Medium';
            prioTd.appendChild(prioBadge);
            tr.appendChild(prioTd);

            depsTbody.appendChild(tr);
        });
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
    function setFormLoading(loading, isConfluence = false) {
        if (isConfluence) {
            confluenceUrlInput.disabled = loading;
            confluenceSubmitBtn.disabled = loading;
            if (loading) {
                confluenceSubmitBtn.classList.add('btn--loading');
            } else {
                confluenceSubmitBtn.classList.remove('btn--loading');
            }
        } else {
            urlInput.disabled       = loading;
            submitBtn.disabled      = loading;
            if (loading) {
                submitBtn.classList.add('btn--loading');
            } else {
                submitBtn.classList.remove('btn--loading');
            }
        }
    }

    // ── Reset UI ─────────────────────────────────────────────────────────────
    function resetUI() {
        logBody.innerHTML = '';
        if (logPlaceholder) {
            logBody.appendChild(logPlaceholder);
            logPlaceholder.style.display = 'block';
        }

        hideBanner();
        progressSteps.classList.remove('progress-steps--visible');
        currentStepIndex = -1;
        resultsSection.style.display = 'none';

        // Hide results panel & error hint
        if (resultsPanel) resultsPanel.style.display = 'none';
        if (errorHint) errorHint.style.display = 'none';

        if (currentEventSource) {
            currentEventSource.close();
            currentEventSource = null;
        }
    }
})();
