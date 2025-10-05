/**
 * MAGIN Frontend - JavaScript API Integration
 *
 * Features:
 * - POST /api/judge with simple_mode support
 * - GET /api/history with pagination
 * - Real-time AI response visualization
 * - 4-aspect scores display
 * - Hard flag warning display
 * - Judgment severity color coding
 * - Error handling and loading states
 * - Simple mode toggle
 * - History modal
 */

// ============================================================
// Configuration
// ============================================================

const API_BASE_URL = '';
const POLL_INTERVAL = 1000; // Progress polling interval (ms)
const TYPEWRITER_SPEED = 50; // Typewriter effect speed (ms/char)

// Decision color mapping (共通定義)
const DECISION_COLOR_MAP = {
    '承認': 'decision-approved',
    '条件付き承認': 'decision-conditional',
    '部分的承認': 'decision-conditional',
    '否決': 'decision-rejected',
    'NOT_APPLICABLE': 'decision-not-applicable'
};

// ============================================================
// Global State
// ============================================================

let currentJudgment = null;
let judgmentInProgress = false;
let simpleMode = false;

// ============================================================
// DOM Elements
// ============================================================

const elements = {
    // Input
    agendaInput: document.getElementById('agenda-input'),
    startBtn: document.getElementById('startBtn'),
    historyBtn: document.getElementById('historyBtn'),

    // Mode toggle
    modeToggle: document.getElementById('modeToggle'),

    // Progress
    progressSection: document.getElementById('progressSection'),
    progressFill: document.getElementById('progressFill'),
    progressText: document.getElementById('progressText'),

    // MAGI system
    magiWrapper: document.getElementById('magi-system-wrapper'),
    statusText: document.getElementById('status-text'),
    finalResult: document.getElementById('finalResult'),
    finalDecisionText: document.getElementById('finalDecisionText'),

    // AI Units
    gemini: document.getElementById('gemini'),
    claude: document.getElementById('claude'),
    chatgpt: document.getElementById('chatgpt'),

    // AI Status
    statusGemini: document.getElementById('status-gemini'),
    statusClaude: document.getElementById('status-claude'),
    statusChatgpt: document.getElementById('status-chatgpt'),
    statusChatGPT: document.getElementById('status-chatgpt'), // Alias for special case

    // Pipes
    pipeG: document.getElementById('pipe-g'),
    pipeC1: document.getElementById('pipe-c1'),
    pipeC2: document.getElementById('pipe-c2'),
    pipeCh1: document.getElementById('pipe-ch1'),
    pipeCh2: document.getElementById('pipe-ch2'),

    // Summary
    summaryReport: document.getElementById('summaryReport'),
    summaryDecision: document.getElementById('summaryDecision'),
    summarySeverity: document.getElementById('summarySeverity'),
    summaryReasoning: document.getElementById('summaryReasoning'),

    // Simple mode
    simpleOutput: document.getElementById('simpleOutput'),

    // Modals
    aiModal: document.getElementById('aiModal'),
    closeAIModal: document.getElementById('closeAIModal'),
    historyModal: document.getElementById('historyModal'),
    closeHistoryModal: document.getElementById('closeHistoryModal'),
    historyTableBody: document.getElementById('historyTableBody')
};

// ============================================================
// API Functions
// ============================================================

/**
 * Submit judgment to backend API
 * @param {string} issue - Issue to judge
 * @param {boolean} simple_mode - Simple mode flag
 * @returns {Promise<Object>} - Judgment result
 */
async function submitJudgment(issue, simple_mode = false) {
    const response = await fetch(`${API_BASE_URL}/api/judge`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ issue, simple_mode })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || `HTTP ${response.status}`);
    }

    return await response.json();
}

/**
 * Load judgment history from backend
 * @param {number} limit - Maximum number of records
 * @param {number} offset - Pagination offset
 * @returns {Promise<Object>} - History data with pagination
 */
async function loadHistory(limit = 100, offset = 0) {
    const response = await fetch(`${API_BASE_URL}/api/history?limit=${limit}&offset=${offset}`);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
}

// ============================================================
// UI Helper Functions
// ============================================================

/**
 * Reset UI to initial state
 */
function resetUI() {
    elements.statusText.textContent = 'STANDBY';
    elements.finalResult.style.display = 'none';
    elements.finalDecisionText.textContent = '';
    elements.progressFill.style.width = '0%';
    elements.progressText.textContent = '0% (0/3 COMPLETE)';
    elements.summaryReport.style.display = 'none';

    // Reset AI units
    const ais = ['gemini', 'claude', 'chatgpt'];
    ais.forEach(ai => {
        elements[ai].className = 'ai-unit';
        elements[`status${ai.charAt(0).toUpperCase() + ai.slice(1)}`].textContent = 'IDLE';
    });

    // Reset pipes
    [elements.pipeG, elements.pipeC1, elements.pipeC2, elements.pipeCh1, elements.pipeCh2].forEach(pipe => {
        pipe.classList.remove('active');
    });
}

/**
 * Update progress bar
 * @param {number} completedCount - Number of completed AI responses
 */
function updateProgress(completedCount) {
    const progress = (completedCount / 3) * 100;
    elements.progressFill.style.width = `${progress}%`;
    elements.progressText.textContent = `${Math.floor(progress)}% (${completedCount}/3 COMPLETE)`;

    // Update simple mode progress
    if (simpleMode) {
        elements.simpleOutput.innerHTML = `<div style="color: #2196f3;">⏳ JUDGMENT IN PROGRESS... (${completedCount}/3 AI COMPLETED)</div>`;
    }
}

/**
 * Typewriter effect for text display
 * @param {HTMLElement} element - Target element
 * @param {string} text - Text to display
 * @param {number} speed - Speed in ms per character
 * @param {Function} callback - Callback after completion
 */
function typeWriter(element, text, speed = TYPEWRITER_SPEED, callback) {
    let i = 0;
    element.innerHTML = '';

    function type() {
        if (i < text.length) {
            element.innerHTML += text.charAt(i);
            i++;
            setTimeout(type, speed);
        } else if (callback) {
            setTimeout(callback, 500);
        }
    }
    type();
}

/**
 * Get severity level from judgment_severity score
 * @param {number} severity - Severity score (0-100)
 * @returns {string} - Severity level (HIGH/MID/LOW)
 */
function getSeverityLevel(severity) {
    if (severity >= 75) return 'HIGH';
    if (severity >= 40) return 'MID';
    return 'LOW';
}

/**
 * Get severity CSS class
 * @param {string} level - Severity level (HIGH/MID/LOW)
 * @returns {string} - CSS class name
 */
function getSeverityClass(level) {
    if (level === 'HIGH') return 'severity-high';
    if (level === 'MID') return 'severity-mid';
    return 'severity-low';
}

/**
 * Map Japanese decision to English
 * @param {string} decision - Japanese decision
 * @returns {string} - English decision
 */
function mapDecision(decision) {
    if (!decision) return '---';
    const map = {
        '承認': 'APPROVED',
        '部分的承認': 'PARTIAL APPROVAL',
        '否決': 'REJECTED',
        '条件付き承認': 'CONDITIONAL APPROVAL',
        'NOT_APPLICABLE': 'NOT APPLICABLE'
    };
    return map[decision] || decision.toUpperCase();
}

// ============================================================
// AI Response Visualization
// ============================================================

/**
 * Update AI unit display with response data
 * @param {string} aiName - AI name (gemini/claude/chatgpt)
 * @param {Object} data - AI response data
 */
function updateAIUnit(aiName, data) {
    const unit = elements[aiName];
    // Handle special case for ChatGPT status element
    const statusKey = aiName === 'chatgpt' ? 'statusChatGPT' : `status${aiName.charAt(0).toUpperCase() + aiName.slice(1)}`;
    const status = elements[statusKey];

    if (!data) {
        // AI failed
        unit.classList.remove('thinking');
        unit.classList.add('error');
        status.textContent = '✗ FAILED';
        return;
    }

    // AI completed successfully
    unit.classList.remove('thinking');

    // Show decision in status and set color
    if (data.decision) {
        const decisionMap = {
            '承認': '✓ APPROVED',
            '条件付き承認': '△ CONDITIONAL',
            '部分的承認': '△ PARTIAL',
            '否決': '✗ REJECTED',
            'NOT_APPLICABLE': '- N/A'
        };
        status.textContent = decisionMap[data.decision] || `✓ ${data.decision}`;

        // Set unit color based on decision
        if (data.decision === '否決') {
            unit.classList.remove('complete');
            unit.classList.add('error'); // Red color for REJECTED
        } else if (data.decision === 'NOT_APPLICABLE') {
            unit.classList.remove('complete');
            unit.classList.add('not-applicable'); // Gray color for NOT_APPLICABLE
        } else if (data.decision === '条件付き承認' || data.decision === '部分的承認') {
            unit.classList.remove('complete');
            unit.classList.add('conditional'); // Yellow for CONDITIONAL/PARTIAL
        } else {
            unit.classList.add('complete'); // Green for approved
        }
    } else {
        unit.classList.add('complete');
        status.textContent = '✓ COMPLETE';
    }

    // Activate pipes
    const pipes = {
        gemini: [elements.pipeG],
        claude: [elements.pipeC1, elements.pipeC2],
        chatgpt: [elements.pipeCh1, elements.pipeCh2]
    };

    pipes[aiName].forEach(pipe => pipe.classList.add('active'));
}

/**
 * Show AI detail modal
 * @param {string} aiName - AI name (gemini/claude/chatgpt)
 */
function showAIDetail(aiName) {
    if (!currentJudgment || !currentJudgment[aiName]) return;

    const data = currentJudgment[aiName];
    const aiNames = {
        gemini: 'GEMINI',
        claude: 'CLAUDE',
        chatgpt: 'CHATGPT'
    };

    // Set title
    document.getElementById('aiModalTitle').textContent = `${aiNames[aiName]} DETAIL`;

    // Check if AI failed
    if (data.failed) {
        // Show failure message
        document.getElementById('aiModalValidity').textContent = '---';
        document.getElementById('aiModalFeasibility').textContent = '---';
        document.getElementById('aiModalRisk').textContent = '---';
        document.getElementById('aiModalCertainty').textContent = '---';
        document.getElementById('hardFlagSection').style.display = 'none';
        document.getElementById('aiModalDecision').textContent = 'FAILED';
        document.getElementById('aiModalSeverity').textContent = '---';
        document.getElementById('aiModalReason').textContent = data.raw_output || data.error || 'AI request failed';

        const concernsList = document.getElementById('aiModalConcerns');
        concernsList.innerHTML = '';
        const li = document.createElement('li');
        li.textContent = 'AI DID NOT RESPOND';
        li.style.color = '#f44336';
        concernsList.appendChild(li);

        elements.aiModal.classList.add('active');
        return;
    }

    // Display 4-aspect scores
    document.getElementById('aiModalValidity').textContent = data.scores.validity.toFixed(2);
    document.getElementById('aiModalFeasibility').textContent = data.scores.feasibility.toFixed(2);
    document.getElementById('aiModalRisk').textContent = data.scores.risk.toFixed(2);
    document.getElementById('aiModalCertainty').textContent = data.scores.certainty.toFixed(2);

    // Display hard flag if present
    const hardFlagSection = document.getElementById('hardFlagSection');
    if (data.hard_flag && data.hard_flag !== 'none') {
        hardFlagSection.style.display = 'block';
        document.getElementById('aiModalHardFlag').textContent = data.hard_flag.toUpperCase();
    } else {
        hardFlagSection.style.display = 'none';
    }

    // Display decision and severity
    document.getElementById('aiModalDecision').textContent = mapDecision(data.decision);
    document.getElementById('aiModalSeverity').textContent = `${data.severity} / 100`;
    document.getElementById('aiModalReason').textContent = data.reason;

    // Display concerns
    const concernsList = document.getElementById('aiModalConcerns');
    concernsList.innerHTML = '';
    if (data.concerns && data.concerns.length > 0) {
        data.concerns.forEach(concern => {
            const li = document.createElement('li');
            li.textContent = concern;
            concernsList.appendChild(li);
        });
    } else {
        const li = document.createElement('li');
        li.textContent = 'NO CONCERNS IDENTIFIED';
        li.style.color = '#666';
        concernsList.appendChild(li);
    }

    elements.aiModal.classList.add('active');
}

// ============================================================
// Judgment Execution
// ============================================================

/**
 * Start judgment process with SSE (real-time updates)
 */
async function startJudgment() {
    if (judgmentInProgress) return;

    const issue = elements.agendaInput.value.trim();
    if (!issue) {
        alert('PLEASE INPUT PROPOSITION');
        return;
    }

    if (issue.length < 1) {
        alert('PLEASE INPUT PROPOSITION');
        return;
    }

    // Start judgment
    judgmentInProgress = true;
    elements.startBtn.disabled = true;
    elements.magiWrapper.style.display = 'block';
    elements.progressSection.style.display = 'block';
    resetUI();

    // Show progress in simple mode
    if (simpleMode) {
        elements.simpleOutput.innerHTML = '<div style="color: #2196f3;">⏳ JUDGMENT IN PROGRESS...</div>';
    }

    elements.statusText.textContent = 'DELIBERATING...';

    // Set AI units to thinking state
    ['gemini', 'claude', 'chatgpt'].forEach(ai => {
        elements[ai].classList.add('thinking');
        elements[`status${ai.charAt(0).toUpperCase() + ai.slice(1)}`].textContent = 'ANALYZING...';
    });

    updateProgress(0);

    // Auto scroll to DELIBERATION PROGRESS (top of screen)
    setTimeout(() => {
        elements.progressSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 300);

    try {
        // Use SSE for real-time updates
        const encodedIssue = encodeURIComponent(issue);
        const eventSource = new EventSource(`${API_BASE_URL}/api/judge/stream?issue=${encodedIssue}`);

        let completedCount = 0;
        let finalResultData = null;
        const aiResults = {};

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'ai_complete') {
                // AI completed - update immediately
                const aiName = data.ai.toLowerCase(); // Normalize to lowercase
                const result = data.result;
                aiResults[aiName] = result;

                if (result.success && result.response) {
                    // Extract response data for updateAIUnit
                    updateAIUnit(aiName, result.response);
                    completedCount++;
                    updateProgress(completedCount);
                } else {
                    updateAIUnit(aiName, null);
                }

            } else if (data.type === 'final_result') {
                // Final result received
                finalResultData = data;
                eventSource.close();

                // Calculate avg_severity and judgment_severity from responses
                const responses = data.responses || [];
                const successfulResponses = responses.filter(r => r.success && r.response);
                const avgSeverity = successfulResponses.length > 0
                    ? successfulResponses.reduce((sum, r) => sum + r.response.severity, 0) / successfulResponses.length
                    : 0;

                // Reconstruct AI data from responses
                const aiData = {};
                responses.forEach(r => {
                    const aiName = r.ai.toLowerCase();
                    aiData[aiName] = r.success && r.response ? r.response : {
                        failed: true,
                        error: r.error || 'Unknown error',
                        raw_output: r.raw_output || ''
                    };
                });

                // Store current judgment
                currentJudgment = {
                    issue: issue,
                    result: data.result,
                    reasoning: data.reasoning,
                    severity_level: data.severity_level,
                    avg_severity: avgSeverity,
                    judgment_severity: avgSeverity,
                    gemini: aiData.gemini,
                    claude: aiData.claude,
                    chatgpt: aiData.chatgpt
                };

                // Show final decision
                setTimeout(() => {
                    showFinalDecision(currentJudgment);
                }, 500);

            } else if (data.type === 'error') {
                // Error occurred
                eventSource.close();
                throw new Error(data.error);
            }
        };

        eventSource.onerror = (error) => {
            console.error('SSE error:', error);
            eventSource.close();

            elements.statusText.textContent = 'ERROR';
            alert('CONNECTION ERROR - PLEASE TRY AGAIN');

            // Reset state
            judgmentInProgress = false;
            elements.startBtn.disabled = false;

            // Mark all AIs as failed
            ['gemini', 'claude', 'chatgpt'].forEach(ai => {
                updateAIUnit(ai, null);
            });
        };

    } catch (error) {
        console.error('Judgment failed:', error);
        elements.statusText.textContent = 'ERROR';

        alert(`ERROR: ${error.message}`);

        // Reset state
        judgmentInProgress = false;
        elements.startBtn.disabled = false;

        // Mark all AIs as failed
        ['gemini', 'claude', 'chatgpt'].forEach(ai => {
            updateAIUnit(ai, null);
        });
    }
}

/**
 * Show final decision with animation
 * @param {Object} result - Judgment result
 */
function showFinalDecision(result) {
    elements.statusText.textContent = 'VERDICT REACHED';
    elements.finalResult.style.display = 'block';
    elements.finalDecisionText.classList.add('noise');

    setTimeout(() => {
        elements.finalDecisionText.classList.remove('noise');
        const decision = mapDecision(result.result);

        // Add color class based on decision
        const colorClass = DECISION_COLOR_MAP[result.result] || '';
        if (colorClass) {
            elements.finalDecisionText.classList.add(colorClass);
        }

        typeWriter(elements.finalDecisionText, decision, TYPEWRITER_SPEED, () => {
            judgmentInProgress = false;
            elements.startBtn.disabled = false;

            // Show summary report
            setTimeout(() => {
                showSummaryReport(result);

                // Auto scroll to show entire FINAL VERDICT SUMMARY after 0.5 seconds
                setTimeout(() => {
                    // Scroll to ensure the entire summary is visible
                    const summaryBottom = elements.summaryReport.getBoundingClientRect().bottom;
                    const windowHeight = window.innerHeight;

                    if (summaryBottom > windowHeight) {
                        elements.summaryReport.scrollIntoView({ behavior: 'smooth', block: 'end' });
                    } else {
                        elements.summaryReport.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }, 500);
            }, 1000);

            // Update simple mode output if active
            if (simpleMode) {
                updateSimpleOutput(result);
            }
        });
    }, 600);
}

/**
 * Show summary report
 * @param {Object} result - Judgment result
 */
function showSummaryReport(result) {
    const severityLevel = result.severity_level || getSeverityLevel(result.judgment_severity || result.avg_severity);
    const severityClass = getSeverityClass(severityLevel);

    // Decision color based on result type
    const decisionClass = DECISION_COLOR_MAP[result.result] || '';

    elements.summaryDecision.textContent = mapDecision(result.result);
    elements.summaryDecision.className = `summary-value ${decisionClass}`;

    const severityDisplay = result.judgment_severity
        ? `${severityLevel} (${result.judgment_severity.toFixed(1)})`
        : `${severityLevel} (${result.avg_severity.toFixed(1)})`;

    elements.summarySeverity.textContent = severityDisplay;
    elements.summarySeverity.className = `summary-value ${severityClass}`;

    elements.summaryReasoning.textContent = result.reasoning;

    // Check for hard flags from any AI
    const hardFlags = [];
    ['claude', 'gemini', 'chatgpt'].forEach(aiName => {
        const aiData = currentJudgment[aiName];
        if (aiData && !aiData.failed && aiData.hard_flag && aiData.hard_flag !== 'none') {
            hardFlags.push(`${aiName.toUpperCase()}: ${aiData.hard_flag.toUpperCase()}`);
        }
    });

    const hardFlagSection = document.getElementById('summaryHardFlagSection');
    if (hardFlags.length > 0) {
        hardFlagSection.style.display = 'block';
        document.getElementById('summaryHardFlag').textContent = hardFlags.join(', ');
    } else {
        hardFlagSection.style.display = 'none';
    }

    // AI Decisions & Reasoning with color coding
    const updateAIDecisionCompact = (aiName, data) => {
        // Handle special case for ChatGPT (HTML ID uses 'ChatGPT' not 'Chatgpt')
        const idSuffix = aiName === 'chatgpt' ? 'ChatGPT' : aiName.charAt(0).toUpperCase() + aiName.slice(1);
        const el = document.getElementById(`summary${idSuffix}Decision`);
        if (el) {
            const decisionEl = el.querySelector('.decision-compact');
            const reasoningEl = el.querySelector('.reasoning-compact');
            if (data) {
                // Check if AI failed
                if (data.failed) {
                    if (decisionEl) {
                        decisionEl.textContent = 'FAILED';
                        decisionEl.className = 'decision-compact decision-rejected';
                    }
                    if (reasoningEl) {
                        reasoningEl.textContent = data.raw_output || data.error || 'AI request failed';
                    }
                } else {
                    if (decisionEl) {
                        decisionEl.textContent = mapDecision(data.decision);
                        // Apply color class based on decision
                        decisionEl.className = `decision-compact ${DECISION_COLOR_MAP[data.decision] || ''}`;
                    }
                    if (reasoningEl) reasoningEl.textContent = data.reason || data.reasoning || '---';
                }
            } else {
                if (decisionEl) {
                    decisionEl.textContent = '---';
                    decisionEl.className = 'decision-compact';
                }
                if (reasoningEl) reasoningEl.textContent = '---';
            }
        }
    };

    updateAIDecisionCompact('claude', result.claude);
    updateAIDecisionCompact('gemini', result.gemini);
    updateAIDecisionCompact('chatgpt', result.chatgpt);

    elements.summaryReport.style.display = 'block';
    elements.summaryReport.style.animation = 'modalSlideIn 0.5s ease';
}

// ============================================================
// Simple Mode
// ============================================================

/**
 * Toggle simple mode
 */
function toggleMode() {
    simpleMode = !simpleMode;
    elements.modeToggle.classList.toggle('active');
    document.body.classList.toggle('simple-mode');

    if (simpleMode && currentJudgment) {
        updateSimpleOutput(currentJudgment);
    }
}

/**
 * Update simple mode output
 * @param {Object} result - Judgment result
 */
function updateSimpleOutput(result) {
    if (result.plain_text_output) {
        // Use backend-generated plain text output
        elements.simpleOutput.innerHTML = result.plain_text_output +
            '<br><button class="copy-btn" onclick="copyToClipboard()">COPY ALL</button>';
    } else {
        // Fallback: generate plain text output from result
        const output = generatePlainTextOutput(result);
        elements.simpleOutput.innerHTML = output +
            '<br><button class="copy-btn" onclick="copyToClipboard()">COPY ALL</button>';
    }
}

/**
 * Generate plain text output from judgment result
 * @param {Object} result - Judgment result
 * @returns {string} - Plain text output
 */
function generatePlainTextOutput(result) {
    let output = '========================================\n';
    output += `PROPOSITION: ${result.issue}\n`;
    output += '========================================\n';
    output += `FINAL VERDICT: ${mapDecision(result.result)}\n`;

    const severity = result.judgment_severity || result.avg_severity;
    const level = result.severity_level || getSeverityLevel(severity);
    output += `SEVERITY: ${level} (${severity.toFixed(1)})\n\n`;

    output += `REASONING: ${result.reasoning}\n\n`;

    // AI responses
    const ais = [
        { name: 'GEMINI', key: 'gemini' },
        { name: 'CLAUDE', key: 'claude' },
        { name: 'CHATGPT', key: 'chatgpt' }
    ];

    ais.forEach(ai => {
        if (result[ai.key]) {
            const data = result[ai.key];

            // Check if AI failed
            if (data.failed) {
                output += `${ai.name}: FAILED\n`;
                output += `REASON: ${data.raw_output || data.error || 'AI request failed'}\n\n`;
                return;
            }

            output += `${ai.name}: ${mapDecision(data.decision)} (Severity: ${data.severity})\n`;
            output += `SCORES - Validity: ${data.scores.validity.toFixed(2)}, `;
            output += `Feasibility: ${data.scores.feasibility.toFixed(2)}, `;
            output += `Risk: ${data.scores.risk.toFixed(2)}, `;
            output += `Certainty: ${data.scores.certainty.toFixed(2)}\n`;
            output += `REASON: ${data.reason}\n`;
            if (data.hard_flag && data.hard_flag !== 'none') {
                output += `⚠️ HARD FLAG: ${data.hard_flag.toUpperCase()}\n`;
            }
            if (data.concerns && data.concerns.length > 0) {
                output += `CONCERNS: ${data.concerns.join(', ')}\n`;
            }
            output += '\n';
        } else {
            output += `${ai.name}: FAILED\n\n`;
        }
    });

    output += '========================================';
    return output;
}

/**
 * Copy text to clipboard
 */
function copyToClipboard() {
    const text = elements.simpleOutput.textContent.replace('COPY ALL', '').trim();
    navigator.clipboard.writeText(text).then(() => {
        alert('COPIED TO CLIPBOARD');
    }).catch(err => {
        console.error('Copy failed:', err);
        alert('COPY FAILED');
    });
}

// ============================================================
// History Management
// ============================================================

/**
 * Show history modal
 */
async function showHistory() {
    try {
        const history = await loadHistory(100, 0);

        elements.historyTableBody.innerHTML = '';

        if (!history.items || history.items.length === 0) {
            elements.historyTableBody.innerHTML =
                '<tr><td colspan="5" style="text-align: center; color: #666;">NO HISTORY DATA</td></tr>';
        } else {
            history.items.forEach(item => {
                const row = elements.historyTableBody.insertRow();

                const date = new Date(item.created_at);
                const dateStr = date.toLocaleDateString('ja-JP');

                const truncatedIssue = item.issue.length > 40
                    ? item.issue.substring(0, 40) + '...'
                    : item.issue;

                const severity = item.judgment_severity || item.avg_severity;
                const level = item.severity_level || getSeverityLevel(severity);
                const severityClass = getSeverityClass(level);

                const resultClass = DECISION_COLOR_MAP[item.result] || '';

                row.innerHTML = `
                    <td>${dateStr}</td>
                    <td>${truncatedIssue}</td>
                    <td class="${resultClass}">${mapDecision(item.result)}</td>
                    <td class="${severityClass}">${level} (${severity.toFixed(1)})</td>
                    <td><button class="view-detail-btn" onclick="viewHistoryDetail(${item.id})">DETAIL</button></td>
                `;
            });
        }

        elements.historyModal.classList.add('active');

    } catch (error) {
        console.error('Failed to load history:', error);
        alert('FAILED TO LOAD HISTORY');
    }
}

/**
 * View history detail
 * @param {number} id - Judgment ID
 */
async function viewHistoryDetail(id) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/history/${id}`);
        if (!response.ok) throw new Error('NOT FOUND');

        const judgment = await response.json();

        // 履歴詳細モーダルに表示
        document.getElementById('detailIssue').textContent = judgment.issue;

        const detailResultEl = document.getElementById('detailResult');
        detailResultEl.textContent = mapDecision(judgment.result);

        // Add color class to FINAL VERDICT
        detailResultEl.className = `detail-value ${DECISION_COLOR_MAP[judgment.result] || ''}`;

        // AI判断結果 (null check, handle both 'reason' and 'reasoning' fields)
        // AI Decisions with color coding

        const claudeDecisionEl = document.getElementById('detailClaudeDecision');
        if (judgment.claude) {
            if (judgment.claude.failed) {
                claudeDecisionEl.textContent = 'FAILED';
                claudeDecisionEl.className = 'detail-value decision-rejected';
                document.getElementById('detailClaudeReasoning').textContent =
                    judgment.claude.raw_output || judgment.claude.error || 'AI request failed';
            } else {
                claudeDecisionEl.textContent = mapDecision(judgment.claude.decision);
                claudeDecisionEl.className = `detail-value ${DECISION_COLOR_MAP[judgment.claude.decision] || ''}`;
                document.getElementById('detailClaudeReasoning').textContent =
                    judgment.claude.reasoning || judgment.claude.reason || '---';
            }
        } else {
            claudeDecisionEl.textContent = '---';
            claudeDecisionEl.className = 'detail-value';
            document.getElementById('detailClaudeReasoning').textContent = '---';
        }

        const geminiDecisionEl = document.getElementById('detailGeminiDecision');
        if (judgment.gemini) {
            if (judgment.gemini.failed) {
                geminiDecisionEl.textContent = 'FAILED';
                geminiDecisionEl.className = 'detail-value decision-rejected';
                document.getElementById('detailGeminiReasoning').textContent =
                    judgment.gemini.raw_output || judgment.gemini.error || 'AI request failed';
            } else {
                geminiDecisionEl.textContent = mapDecision(judgment.gemini.decision);
                geminiDecisionEl.className = `detail-value ${DECISION_COLOR_MAP[judgment.gemini.decision] || ''}`;
                document.getElementById('detailGeminiReasoning').textContent =
                    judgment.gemini.reasoning || judgment.gemini.reason || '---';
            }
        } else {
            geminiDecisionEl.textContent = '---';
            geminiDecisionEl.className = 'detail-value';
            document.getElementById('detailGeminiReasoning').textContent = '---';
        }

        const chatgptDecisionEl = document.getElementById('detailChatGPTDecision');
        if (judgment.chatgpt) {
            if (judgment.chatgpt.failed) {
                chatgptDecisionEl.textContent = 'FAILED';
                chatgptDecisionEl.className = 'detail-value decision-rejected';
                document.getElementById('detailChatGPTReasoning').textContent =
                    judgment.chatgpt.raw_output || judgment.chatgpt.error || 'AI request failed';
            } else {
                chatgptDecisionEl.textContent = mapDecision(judgment.chatgpt.decision);
                chatgptDecisionEl.className = `detail-value ${DECISION_COLOR_MAP[judgment.chatgpt.decision] || ''}`;
                document.getElementById('detailChatGPTReasoning').textContent =
                    judgment.chatgpt.reasoning || judgment.chatgpt.reason || '---';
            }
        } else {
            chatgptDecisionEl.textContent = '---';
            chatgptDecisionEl.className = 'detail-value';
            document.getElementById('detailChatGPTReasoning').textContent = '---';
        }

        // 重大度 (calculate severity_level if missing)
        const severityValue = judgment.judgment_severity || judgment.avg_severity || 0;
        const severityLevel = judgment.severity_level || (
            severityValue >= 70 ? 'HIGH' :
            severityValue >= 40 ? 'MID' : 'LOW'
        );
        const severityClass = getSeverityClass(severityLevel);
        document.getElementById('detailSeverity').textContent =
            `${severityLevel} (${severityValue.toFixed(1)})`;
        document.getElementById('detailSeverity').className = `detail-value ${severityClass}`;

        // 履歴詳細モーダルを表示（履歴モーダルは閉じない）
        document.getElementById('historyDetailModal').classList.add('active');

    } catch (error) {
        console.error('Failed to load judgment detail:', error);
        alert('FAILED TO LOAD DETAIL');
    }
}

// ============================================================
// Event Listeners
// ============================================================

elements.startBtn.addEventListener('click', startJudgment);
elements.historyBtn.addEventListener('click', showHistory);
elements.modeToggle.addEventListener('click', toggleMode);

// AI unit click handlers
elements.gemini.addEventListener('click', () => showAIDetail('gemini'));
elements.claude.addEventListener('click', () => showAIDetail('claude'));
elements.chatgpt.addEventListener('click', () => showAIDetail('chatgpt'));

// Modal close handlers
elements.closeAIModal.addEventListener('click', () => {
    elements.aiModal.classList.remove('active');
});

elements.closeHistoryModal.addEventListener('click', () => {
    elements.historyModal.classList.remove('active');
});

document.getElementById('closeHistoryDetailModal').addEventListener('click', () => {
    document.getElementById('historyDetailModal').classList.remove('active');
});

// Click outside modal to close
elements.aiModal.addEventListener('click', (e) => {
    if (e.target === elements.aiModal) {
        elements.aiModal.classList.remove('active');
    }
});

elements.historyModal.addEventListener('click', (e) => {
    if (e.target === elements.historyModal) {
        elements.historyModal.classList.remove('active');
    }
});

// Enter key to submit
elements.agendaInput.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') {
        startJudgment();
    }
});

// ============================================================
// Initialization
// ============================================================

// Generate SESSION_ID (random 8-char alphanumeric)
function generateSessionId() {
    return Math.random().toString(36).substring(2, 10).toUpperCase();
}

// Update SYSTEM_TIME (JST)
function updateSystemTime() {
    const now = new Date();
    const jstTime = new Intl.DateTimeFormat('ja-JP', {
        timeZone: 'Asia/Tokyo',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    }).format(now);
    const sessionTimeEl = document.getElementById('system-time');
    if (sessionTimeEl) {
        sessionTimeEl.textContent = jstTime;
    }
}

// Initialize session ID and time
const sessionIdEl = document.getElementById('session-id');
if (sessionIdEl) {
    sessionIdEl.textContent = generateSessionId();
}
updateSystemTime();
setInterval(updateSystemTime, 60000); // Update every minute

