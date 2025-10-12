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

// Sound effects
const SOUNDS = {
    judgmentStart: '/sounds/judgement_start.mp3',
    nodeVerdict: '/sounds/node_verdict.mp3',
    finalVerdict: '/sounds/final_verdict.mp3'
};

/**
 * Play sound effect
 * @param {string} soundPath - Path to sound file
 * @param {number} volume - Volume (0.0-1.0), default 0.15
 */
function playSound(soundPath, volume = 0.15) {
    if (!soundEnabled) return; // Skip if SE is OFF

    try {
        const audio = new Audio(soundPath);
        audio.volume = volume;
        audio.play().catch(err => {
            console.warn('Sound play failed:', err);
        });
    } catch (error) {
        console.warn('Sound not available:', error);
    }
}

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
let soundEnabled = false; // SE is OFF by default

// Initialize mode toggle state (SIMPLE is on the left, so default OFF means FULL MODE)
// After DOM loads, we need to set initial state correctly

// ============================================================
// DOM Elements
// ============================================================

const elements = {
    // Input
    agendaInput: document.getElementById('agenda-input'),
    startBtn: document.getElementById('startBtn'),
    historyBtn: document.getElementById('historyBtn'),
    configBtn: document.getElementById('configBtn'),

    // Mode toggle
    modeToggle: document.getElementById('modeToggle'),
    seToggle: document.getElementById('seToggle'),

    // Progress
    progressSection: document.getElementById('progressSection'),
    progressFill: document.getElementById('progressFill'),
    progressText: document.getElementById('progressText'),

    // MAGI system
    magiWrapper: document.getElementById('magi-system-wrapper'),
    statusText: document.getElementById('status-text'),
    finalResult: document.getElementById('finalResult'),
    finalDecisionText: document.getElementById('finalDecisionText'),
    linkingCircle: document.getElementById('linking-circle'),

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
    summaryConditional: document.getElementById('summaryConditional'),
    summarySeverity: document.getElementById('summarySeverity'),

    // Simple mode
    simpleOutput: document.getElementById('simpleOutput'),

    // Modals
    aiModal: document.getElementById('aiModal'),
    closeAIModal: document.getElementById('closeAIModal'),
    historyModal: document.getElementById('historyModal'),
    closeHistoryModal: document.getElementById('closeHistoryModal'),
    historyTableBody: document.getElementById('historyTableBody'),

    // Config Modal (v1.2)
    configModal: document.getElementById('configModal'),
    closeConfigModal: document.getElementById('closeConfigModal'),
    persona1: document.getElementById('persona1'),
    persona2: document.getElementById('persona2'),
    persona3: document.getElementById('persona3'),
    saveConfigBtn: document.getElementById('saveConfigBtn'),
    resetConfigBtn: document.getElementById('resetConfigBtn')
};

// ============================================================
// API Functions
// ============================================================

/**
 * Submit judgment to backend API (v1.2 updated)
 * @param {string} issue - Issue to judge
 * @param {boolean} simple_mode - Simple mode flag
 * @returns {Promise<Object>} - Judgment result
 */
async function submitJudgment(issue, simple_mode = false) {
    // Load persona config (v1.2)
    const config = loadConfig();
    const persona_ids = [config.persona1, config.persona2, config.persona3];

    const response = await fetch(`${API_BASE_URL}/api/judge`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            issue,
            simple_mode,
            persona_ids // NEW: Send persona_ids to backend
        })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || `HTTP ${response.status}`);
    }

    const result = await response.json();

    // Store result in global variable for summary copy feature (v1.2)
    currentJudgment = result;

    return result;
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

/**
 * Load personas from backend (v1.2)
 * @returns {Promise<Array>} - Persona list
 */
async function loadPersonas() {
    const response = await fetch(`${API_BASE_URL}/api/personas`);

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.personas;
}

// ============================================================
// Summary Generation (v1.2)
// ============================================================

/**
 * Truncate text with ellipsis if exceeds max length
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length
 * @returns {string} - Truncated text
 */
function truncate(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

/**
 * Generate summary text for clipboard copy (v1.2)
 * @param {Object} result - Judgment result from API
 * @returns {string} - Formatted summary text
 */
function generateSummary(result) {
    if (!result) {
        console.warn('generateSummary called with null result');
        return '';
    }

    // Default persona names
    const defaultPersonaNames = {
        claude: '研究者',
        gemini: '母',
        chatgpt: '女性'
    };

    // Get persona names (from API or defaults)
    const personaNames = result.persona_names || defaultPersonaNames;

    // Truncate persona names (max 50 chars)
    const claudePersona = truncate(personaNames.claude || defaultPersonaNames.claude, 50);
    const geminiPersona = truncate(personaNames.gemini || defaultPersonaNames.gemini, 50);
    const chatgptPersona = truncate(personaNames.chatgpt || defaultPersonaNames.chatgpt, 50);

    // Extract AI responses
    const claude = result.claude || result.ai_responses?.[0];
    const gemini = result.gemini || result.ai_responses?.[1];
    const chatgpt = result.chatgpt || result.ai_responses?.[2];

    // Get engine names (v1.3)
    const engineLabels = {
        'API_Gemini': 'GEMINI API',
        'API_OpenRouter': 'OPENROUTER',
        'API_Ollama': 'OLLAMA',
        'Claude': 'CLAUDE',
        'Gemini': 'GEMINI',
        'ChatGPT': 'CHATGPT'
    };
    const geminiEngine = result.ai_engines?.gemini ? (engineLabels[result.ai_engines.gemini] || result.ai_engines.gemini) : 'GEMINI';
    const claudeEngine = result.ai_engines?.claude ? (engineLabels[result.ai_engines.claude] || result.ai_engines.claude) : 'CLAUDE';
    const chatgptEngine = result.ai_engines?.chatgpt ? (engineLabels[result.ai_engines.chatgpt] || result.ai_engines.chatgpt) : 'CHATGPT';

    // Format AI decision lines with new format
    const formatAILine = (aiName, persona, aiData) => {
        if (!aiData || aiData.decision === 'FAILED') {
            return `• ${aiName} / ERROR / ${persona}\nNo response`;
        }
        const decision = mapDecision(aiData.decision) || 'UNKNOWN';
        const reason = aiData.reason || aiData.reasoning || 'No reason provided';
        return `• ${aiName} / ${decision} / ${persona}\n${reason}`;
    };

    const geminiLine = formatAILine(geminiEngine, geminiPersona, gemini);
    const claudeLine = formatAILine(claudeEngine, claudePersona, claude);
    const chatgptLine = formatAILine(chatgptEngine, chatgptPersona, chatgpt);

    // Build summary (NODE order: Gemini → Claude → ChatGPT)
    let summary = '';
    summary += `PROPOSITION: ${result.issue}\n`;
    summary += `FINAL VERDICT: ${mapDecision(result.result)} / ${(result.total_score ?? 0).toFixed(1)}\n`;
    summary += `SEVERITY: ${result.severity_level} (${Math.round(result.judgment_severity || result.severity || 0)}%)\n`;
    summary += `\n`;
    summary += `${geminiLine}\n`;
    summary += `\n`;
    summary += `${claudeLine}\n`;
    summary += `\n`;
    summary += `${chatgptLine}`;

    // Add hard flag warning if present
    if (result.hard_flags && result.hard_flags.length > 0) {
        summary += `\n\n⚠️ CRITICAL: ${result.hard_flags.join(', ')}`;
    }

    // Check constraints (1000 chars, 15 lines)
    const lineCount = summary.split('\n').length;
    if (summary.length > 1000 || lineCount > 15) {
        console.warn(`Summary exceeds constraints: ${summary.length} chars, ${lineCount} lines`);
    }

    return summary;
}

/**
 * Copy summary to clipboard (v1.2)
 * @returns {Promise<void>}
 */
async function copySummary() {
    if (!currentJudgment) {
        alert('判定結果がありません');
        return;
    }

    const summary = generateSummary(currentJudgment);

    try {
        // Try Clipboard API first (modern browsers)
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(summary);
            console.log('Summary copied to clipboard (Clipboard API)');
            showCopyFeedback();
        } else {
            // Fallback: textarea method
            console.warn('Clipboard API not available, using fallback');
            copyFallback(summary);
        }
    } catch (error) {
        console.error('Clipboard copy failed:', error);
        // Fallback on error
        copyFallback(summary);
    }
}

/**
 * Fallback clipboard copy using textarea
 * @param {string} text - Text to copy
 */
function copyFallback(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.top = '50%';
    textarea.style.left = '50%';
    textarea.style.transform = 'translate(-50%, -50%)';
    textarea.style.width = '80%';
    textarea.style.maxWidth = '600px';
    textarea.style.height = '400px';
    textarea.style.padding = '20px';
    textarea.style.fontSize = '14px';
    textarea.style.fontFamily = 'monospace';
    textarea.style.background = '#1a1a1a';
    textarea.style.color = '#e0e0e0';
    textarea.style.border = '2px solid var(--orange)';
    textarea.style.borderRadius = '8px';
    textarea.style.zIndex = '10000';
    textarea.readOnly = true;

    document.body.appendChild(textarea);
    textarea.select();

    try {
        const successful = document.execCommand('copy');
        if (successful) {
            console.log('Summary copied to clipboard (fallback)');
            showCopyFeedback();
        } else {
            alert('コピーに失敗しました。手動でコピーしてください。');
        }
    } catch (error) {
        console.error('Fallback copy failed:', error);
        alert('コピーに失敗しました。手動でコピーしてください。');
    }

    // Remove textarea after 3 seconds or on click
    setTimeout(() => {
        if (document.body.contains(textarea)) {
            document.body.removeChild(textarea);
        }
    }, 3000);

    textarea.addEventListener('click', () => {
        document.body.removeChild(textarea);
    });
}

/**
 * Show copy feedback (COPIED TO CLIPBOARD for 2 seconds)
 */
function showCopyFeedback() {
    const copyBtn = document.getElementById('copySummaryBtn');
    if (!copyBtn) return;

    const originalText = copyBtn.textContent;
    copyBtn.textContent = 'COPIED TO CLIPBOARD';
    copyBtn.disabled = true;

    setTimeout(() => {
        copyBtn.textContent = originalText;
        copyBtn.disabled = false;
    }, 2000);
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
    if (severity >= 80) return 'HIGH';
    if (severity >= 50) return 'MID';
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

    // Null check: prevent crash if unit element not found
    if (!unit) {
        console.error(`AI unit not found for: ${aiName}`);
        return;
    }

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

    // Play node verdict sound
    playSound(SOUNDS.nodeVerdict);

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

    // Determine engine name for title
    let engineName = aiName.toUpperCase();
    if (currentJudgment.ai_engines && currentJudgment.ai_engines[aiName]) {
        const engineLabels = {
            'API_Gemini': 'GEMINI API',
            'API_OpenRouter': 'OPENROUTER',
            'API_Ollama': 'OLLAMA',
            'Claude': 'CLAUDE',
            'Gemini': 'GEMINI',
            'ChatGPT': 'CHATGPT'
        };
        engineName = engineLabels[currentJudgment.ai_engines[aiName]] || currentJudgment.ai_engines[aiName];
    }

    // Set title with engine name
    document.getElementById('aiModalTitle').textContent = `${engineName} DETAIL`;

    // Set persona name (if available)
    const personaElem = document.getElementById('aiModalPersona');
    if (currentJudgment.persona_names && currentJudgment.persona_names[aiName]) {
        personaElem.textContent = `Persona: ${currentJudgment.persona_names[aiName]}`;
        personaElem.style.display = 'block';
    } else {
        personaElem.style.display = 'none';
    }

    // Set engine and model (if available)
    const engineModelElem = document.getElementById('aiModalEngineModel');
    if (currentJudgment.ai_engines && currentJudgment.ai_models) {
        const engine = currentJudgment.ai_engines[aiName];
        const model = currentJudgment.ai_models[aiName];
        const engineLabels = {
            'API_Gemini': 'GEMINI API',
            'API_OpenRouter': 'OPENROUTER',
            'API_Ollama': 'OLLAMA',
            'Claude': 'CLAUDE',
            'Gemini': 'GEMINI',
            'ChatGPT': 'CHATGPT'
        };
        const engineLabel = engineLabels[engine] || engine;
        engineModelElem.textContent = `Engine: ${engineLabel} | Model: ${model}`;
        engineModelElem.style.display = 'block';
    } else {
        engineModelElem.style.display = 'none';
    }

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
    const decisionEl = document.getElementById('aiModalDecision');
    decisionEl.textContent = mapDecision(data.decision);
    // Add color class based on decision
    const decisionColorClass = DECISION_COLOR_MAP[data.decision] || '';
    decisionEl.className = `detail-value ${decisionColorClass}`;

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

    // Play judgment start sound
    playSound(SOUNDS.judgmentStart);

    // Show progress in simple mode
    if (simpleMode) {
        elements.simpleOutput.innerHTML = '<div style="color: #2196f3;">⏳ JUDGMENT IN PROGRESS...</div>';
    }

    elements.statusText.textContent = 'DELIBERATING...';

    // Load actual backend config and update AI unit labels (v1.3)
    try {
        const configResponse = await fetch(`${API_BASE_URL}/api/config`);
        if (configResponse.ok) {
            const config = await configResponse.json();
            const aiMapping = ['gemini', 'claude', 'chatgpt'];
            const engineLabels = {
                'Claude': 'CLAUDE',
                'Gemini': 'GEMINI',
                'ChatGPT': 'CHATGPT',
                'API_Gemini': 'GEMINI API',
                'API_OpenRouter': 'OPENROUTER',
                'API_Ollama': 'OLLAMA'
            };

            // config.nodes is array: [{id, name, engine, model, persona_id}, ...]
            config.nodes.forEach((node, index) => {
                if (index < 3) {
                    const legacyName = aiMapping[index];

                    // Update engine label
                    const labelElement = elements[legacyName].querySelector('.ai-unit-name');
                    if (labelElement) {
                        labelElement.textContent = engineLabels[node.engine] || node.engine.toUpperCase();
                    }

                    // Update model label (show only if model is set)
                    const modelElement = elements[legacyName].querySelector('.ai-unit-model');
                    if (modelElement && node.model) {
                        modelElement.textContent = node.model;
                    } else if (modelElement) {
                        modelElement.textContent = '';
                    }
                }
            });
        }
    } catch (error) {
        console.warn('Failed to load backend config for AI labels:', error);
    }

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
        // Load persona config from backend (v1.3: use user_config.json, not localStorage)
        const configResponse = await fetch(`${API_BASE_URL}/api/config`);
        let personaIds = ['neutral_ai', 'neutral_ai', 'neutral_ai']; // Default

        if (configResponse.ok) {
            const backendConfig = await configResponse.json();
            // Extract persona_ids from nodes array
            personaIds = backendConfig.nodes.map(node => node.persona_id || 'neutral_ai');
        }

        // Use SSE for real-time updates
        const encodedIssue = encodeURIComponent(issue);
        const encodedPersonas = encodeURIComponent(JSON.stringify(personaIds));
        const eventSource = new EventSource(`${API_BASE_URL}/api/judge/stream?issue=${encodedIssue}&persona_ids=${encodedPersonas}`);

        let completedCount = 0;
        let finalResultData = null;
        const aiResults = {};

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'ai_complete') {
                // AI completed - update immediately
                // Map NODE names to legacy AI names (v1.3 compatibility)
                // Support both uppercase and lowercase variants
                const nodeToAi = {
                    'NODE 1': 'gemini',
                    'NODE 2': 'claude',
                    'NODE 3': 'chatgpt',
                    'node 1': 'gemini',
                    'node 2': 'claude',
                    'node 3': 'chatgpt'
                };
                const aiName = nodeToAi[data.ai] || data.ai.toLowerCase();
                const result = data.result;
                aiResults[aiName] = result;

                if (result.success && result.response) {
                    // Extract response data for updateAIUnit
                    updateAIUnit(aiName, result.response);
                } else {
                    updateAIUnit(aiName, null);
                }

                // Add flash effect to AI unit (v1.1)
                const aiElement = elements[aiName];
                if (aiElement) {
                    aiElement.classList.add('flash-effect');
                    setTimeout(() => {
                        aiElement.classList.remove('flash-effect');
                    }, 1000); // Remove after 1s (matches animation duration)
                }

                // Update progress regardless of success/failure
                completedCount++;
                updateProgress(completedCount);

                // Trigger triangle link effect when all 3 AIs complete (v1.1)
                if (completedCount === 3) {
                    triggerTriangleLink();
                }

            } else if (data.type === 'final_result') {
                // Final result received
                finalResultData = data;
                eventSource.close();

                // Calculate avg_severity from responses (for backward compatibility)
                const responses = data.responses || [];
                const successfulResponses = responses.filter(r => r.success && r.response);
                const avgSeverity = successfulResponses.length > 0
                    ? successfulResponses.reduce((sum, r) => sum + r.response.severity, 0) / successfulResponses.length
                    : 0;

                // Reconstruct AI data from responses
                const nodeToAiLegacy = {
                    'NODE 1': 'gemini',
                    'NODE 2': 'claude',
                    'NODE 3': 'chatgpt',
                    'node 1': 'gemini',
                    'node 2': 'claude',
                    'node 3': 'chatgpt'
                };
                const aiData = {};
                const aiEngines = {}; // Store engine info
                const aiModels = {}; // Store model info
                responses.forEach(r => {
                    const legacyName = nodeToAiLegacy[r.ai] || r.ai.toLowerCase();
                    aiData[legacyName] = r.success && r.response ? r.response : {
                        failed: true,
                        error: r.error || 'Unknown error',
                        raw_output: r.raw_output || ''
                    };
                    // Store engine and model info
                    aiEngines[legacyName] = r.engine || 'Unknown';
                    aiModels[legacyName] = r.model || 'default';
                });

                // Store current judgment
                currentJudgment = {
                    issue: issue,
                    result: data.result,
                    reasoning: data.reasoning,
                    severity_level: data.severity_level,
                    total_score: data.total_score,
                    avg_severity: avgSeverity,
                    judgment_severity: data.judgment_severity,
                    gemini: aiData.gemini,
                    claude: aiData.claude,
                    chatgpt: aiData.chatgpt,
                    persona_names: data.persona_names || {},
                    ai_engines: aiEngines,
                    ai_models: aiModels
                };

                // Show final decision (wait for triangle effect to complete)
                setTimeout(() => {
                    showFinalDecision(currentJudgment);
                }, 1200); // Triangle completes at ~800ms, add 400ms breathing room

            } else if (data.type === 'error') {
                // Error occurred
                eventSource.close();

                elements.statusText.textContent = 'ERROR';
                alert(`エラーが発生しました:\n\n${data.error}`);

                // Reset state
                judgmentInProgress = false;
                elements.startBtn.disabled = false;

                // Mark all AIs as failed
                ['gemini', 'claude', 'chatgpt'].forEach(ai => {
                    updateAIUnit(ai, null);
                });
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

    const decision = mapDecision(result.result);

    // Reset all decision color classes, then add the correct one
    elements.finalDecisionText.classList.remove('decision-approved', 'decision-conditional', 'decision-rejected', 'decision-not-applicable');
    const colorClass = DECISION_COLOR_MAP[result.result] || '';
    if (colorClass) {
        elements.finalDecisionText.classList.add(colorClass);
    }

    // Play final verdict sound
    playSound(SOUNDS.finalVerdict);

    // Typewriter display
    typeWriter(elements.finalDecisionText, decision, TYPEWRITER_SPEED, () => {
        judgmentInProgress = false;
        elements.startBtn.disabled = false;

        // Show summary report (use currentJudgment which has the correct judgment_severity)
        setTimeout(() => {
            showSummaryReport(currentJudgment || result);

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

    // Conditional - show total_score with same color as decision
    let totalScore = result.total_score;

    // Fallback: extract from reasoning if total_score not available (for old data)
    if (totalScore === undefined || totalScore === null) {
        const match = result.reasoning?.match(/合計点([\d.]+)\//);
        totalScore = match ? parseFloat(match[1]) : 0;
    }

    elements.summaryConditional.textContent = totalScore.toFixed(1);
    elements.summaryConditional.className = `summary-value ${decisionClass}`;

    // Severity display - with 1 decimal place
    const severityScore = result.judgment_severity || result.avg_severity || 0;
    const severityText = `${severityLevel} (${severityScore.toFixed(1)})`;
    elements.summarySeverity.textContent = severityText;
    elements.summarySeverity.className = `summary-value ${severityClass}`;

    // Check for hard flags from any AI
    const hardFlags = [];
    const engineLabels = {
        'API_Gemini': 'GEMINI API',
        'API_OpenRouter': 'OPENROUTER',
        'API_Ollama': 'OLLAMA',
        'Claude': 'CLAUDE',
        'Gemini': 'GEMINI',
        'ChatGPT': 'CHATGPT'
    };

    ['gemini', 'claude', 'chatgpt'].forEach(aiName => {
        const aiData = currentJudgment[aiName];
        if (aiData && !aiData.failed && aiData.hard_flag && aiData.hard_flag !== 'none') {
            // Get actual engine name from result
            const engineName = result.ai_engines?.[aiName] || aiName;
            const displayName = engineLabels[engineName] || engineName.toUpperCase();
            hardFlags.push(`${displayName}: ${aiData.hard_flag.toUpperCase()}`);
        }
    });

    const hardFlagSection = document.getElementById('summaryHardFlagSection');
    if (hardFlags.length > 0) {
        hardFlagSection.style.display = 'block';
        document.getElementById('summaryHardFlag').textContent = hardFlags.join(', ');
    } else {
        hardFlagSection.style.display = 'none';
    }

    // Get persona names - prioritize actual judgment data over config
    const personaNames = result.persona_names || currentJudgment?.persona_names || getPersonaNames();
    const defaultPersonaNames = {
        claude: DEFAULT_PERSONAS.persona1,
        gemini: DEFAULT_PERSONAS.persona2,
        chatgpt: DEFAULT_PERSONAS.persona3
    };

    // AI Decisions & Reasoning with new layout
    const updateAIDecisionRow = (aiName, data) => {
        const idSuffix = aiName === 'chatgpt' ? 'ChatGPT' : aiName.charAt(0).toUpperCase() + aiName.slice(1);
        const personaEl = document.getElementById(`summary${idSuffix}Persona`);
        const reasoningEl = document.getElementById(`summary${idSuffix}Reasoning`);
        const decisionBadgeEl = document.getElementById(`summary${idSuffix}DecisionBadge`);

        // Update AI engine/model display
        const modelEl = document.querySelector(`#summary${idSuffix}Decision .ai-model`);
        if (modelEl && result.ai_engines && result.ai_models) {
            const engine = result.ai_engines[aiName];
            const model = result.ai_models[aiName];
            const engineLabels = {
                'API_Gemini': 'GEMINI API',
                'API_OpenRouter': 'OPENROUTER',
                'API_Ollama': 'OLLAMA',
                'Claude': 'CLAUDE',
                'Gemini': 'GEMINI',
                'ChatGPT': 'CHATGPT'
            };
            const engineLabel = engineLabels[engine] || engine;
            modelEl.textContent = `${engineLabel} (${model})`;
        }

        // Set persona name
        if (personaEl) {
            personaEl.textContent = personaNames[aiName] || defaultPersonaNames[aiName] || 'Unknown';
        }

        if (data) {
            if (data.failed) {
                if (reasoningEl) reasoningEl.textContent = data.raw_output || data.error || 'AI request failed';
                if (decisionBadgeEl) {
                    decisionBadgeEl.textContent = 'FAILED';
                    decisionBadgeEl.className = 'ai-decision-badge decision-rejected';
                }
            } else {
                if (reasoningEl) reasoningEl.textContent = data.reason || data.reasoning || '---';
                if (decisionBadgeEl) {
                    decisionBadgeEl.textContent = mapDecision(data.decision);
                    const colorClass = DECISION_COLOR_MAP[data.decision] || '';
                    decisionBadgeEl.className = `ai-decision-badge ${colorClass}`;
                }
            }
        } else {
            if (reasoningEl) reasoningEl.textContent = '---';
            if (decisionBadgeEl) {
                decisionBadgeEl.textContent = '---';
                decisionBadgeEl.className = 'ai-decision-badge';
            }
        }
    };

    updateAIDecisionRow('claude', result.claude);
    updateAIDecisionRow('gemini', result.gemini);
    updateAIDecisionRow('chatgpt', result.chatgpt);

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
 * Toggle sound effects on/off
 */
function toggleSound() {
    soundEnabled = !soundEnabled;
    elements.seToggle.classList.toggle('active');
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
    output += `SEVERITY: ${level} (${severity.toFixed(1)})\n`;
    output += `CONSENSUS SCORE: ${(result.total_score ?? 0).toFixed(1)}\n\n`;

    // Get persona names (with defaults)
    const defaultPersonaNames = {
        claude: '研究者',
        gemini: '母',
        chatgpt: '女性'
    };
    const personaNames = result.persona_names || defaultPersonaNames;

    // AI responses
    const engineLabels = {
        'API_Gemini': 'GEMINI API',
        'API_OpenRouter': 'OPENROUTER',
        'API_Ollama': 'OLLAMA',
        'Claude': 'CLAUDE',
        'Gemini': 'GEMINI',
        'ChatGPT': 'CHATGPT'
    };
    const ais = [
        { name: 'GEMINI', key: 'gemini' },
        { name: 'CLAUDE', key: 'claude' },
        { name: 'CHATGPT', key: 'chatgpt' }
    ];

    ais.forEach(ai => {
        if (result[ai.key]) {
            const data = result[ai.key];

            // Get engine name (model name omitted for brevity in SIMPLE mode)
            const engine = result.ai_engines?.[ai.key] || ai.name;
            const engineLabel = engineLabels[engine] || engine;

            // Check if AI failed
            if (data.failed) {
                output += `${engineLabel}: FAILED\n`;
                output += `REASON: ${data.raw_output || data.error || 'AI request failed'}\n\n`;
                return;
            }

            output += `${engineLabel}: ${mapDecision(data.decision)} (Severity: ${data.severity})\n`;
            output += `PERSONA: ${personaNames[ai.key] || 'Unknown'}\n`;
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
        // AI Decisions with badge layout (matching FINAL VERDICT SUMMARY)

        // Get persona names (v1.1)
        const personaNames = judgment.persona_names || {};

        // Update AI engine/model labels (v1.3)
        const engineLabels = {
            'API_Gemini': 'GEMINI API',
            'API_OpenRouter': 'OPENROUTER',
            'API_Ollama': 'OLLAMA',
            'Claude': 'CLAUDE',
            'Gemini': 'GEMINI',
            'ChatGPT': 'CHATGPT'
        };
        const aiEngines = judgment.ai_engines || {};
        const aiModels = judgment.ai_models || {};

        // Update Gemini label (NODE 1)
        const geminiModelEl = document.querySelector('#historyDetailModal .ai-decision-row:nth-child(1) .ai-model');
        if (geminiModelEl) {
            if (aiEngines.gemini) {
                const engineLabel = engineLabels[aiEngines.gemini] || aiEngines.gemini;
                const model = aiModels.gemini || 'default';
                geminiModelEl.textContent = `${engineLabel} (${model})`;
            } else {
                geminiModelEl.textContent = '---';
            }
        }

        // Update Claude label (NODE 2)
        const claudeModelEl = document.querySelector('#historyDetailModal .ai-decision-row:nth-child(2) .ai-model');
        if (claudeModelEl) {
            if (aiEngines.claude) {
                const engineLabel = engineLabels[aiEngines.claude] || aiEngines.claude;
                const model = aiModels.claude || 'default';
                claudeModelEl.textContent = `${engineLabel} (${model})`;
            } else {
                claudeModelEl.textContent = '---';
            }
        }

        // Update ChatGPT label (NODE 3)
        const chatgptModelEl = document.querySelector('#historyDetailModal .ai-decision-row:nth-child(3) .ai-model');
        if (chatgptModelEl) {
            if (aiEngines.chatgpt) {
                const engineLabel = engineLabels[aiEngines.chatgpt] || aiEngines.chatgpt;
                const model = aiModels.chatgpt || 'default';
                chatgptModelEl.textContent = `${engineLabel} (${model})`;
            } else {
                chatgptModelEl.textContent = '---';
            }
        }

        const claudeDecisionBadgeEl = document.getElementById('detailClaudeDecisionBadge');
        const claudePersonaEl = document.getElementById('detailClaudePersona');
        if (judgment.claude) {
            if (judgment.claude.failed) {
                claudeDecisionBadgeEl.textContent = 'FAILED';
                claudeDecisionBadgeEl.className = 'ai-decision-badge decision-rejected';
                document.getElementById('detailClaudeReasoning').textContent =
                    judgment.claude.raw_output || judgment.claude.error || 'AI request failed';
            } else {
                claudeDecisionBadgeEl.textContent = mapDecision(judgment.claude.decision);
                claudeDecisionBadgeEl.className = `ai-decision-badge ${DECISION_COLOR_MAP[judgment.claude.decision] || ''}`;
                document.getElementById('detailClaudeReasoning').textContent =
                    judgment.claude.reasoning || judgment.claude.reason || '---';
            }
            // Set persona name if available
            if (personaNames.claude) {
                claudePersonaEl.textContent = personaNames.claude;
                claudePersonaEl.style.display = '';
            } else {
                claudePersonaEl.textContent = '';
                claudePersonaEl.style.display = 'none';
            }
        } else {
            claudeDecisionBadgeEl.textContent = '---';
            claudeDecisionBadgeEl.className = 'ai-decision-badge';
            document.getElementById('detailClaudeReasoning').textContent = '---';
            claudePersonaEl.textContent = '';
            claudePersonaEl.style.display = 'none';
        }

        const geminiDecisionBadgeEl = document.getElementById('detailGeminiDecisionBadge');
        const geminiPersonaEl = document.getElementById('detailGeminiPersona');
        if (judgment.gemini) {
            if (judgment.gemini.failed) {
                geminiDecisionBadgeEl.textContent = 'FAILED';
                geminiDecisionBadgeEl.className = 'ai-decision-badge decision-rejected';
                document.getElementById('detailGeminiReasoning').textContent =
                    judgment.gemini.raw_output || judgment.gemini.error || 'AI request failed';
            } else {
                geminiDecisionBadgeEl.textContent = mapDecision(judgment.gemini.decision);
                geminiDecisionBadgeEl.className = `ai-decision-badge ${DECISION_COLOR_MAP[judgment.gemini.decision] || ''}`;
                document.getElementById('detailGeminiReasoning').textContent =
                    judgment.gemini.reasoning || judgment.gemini.reason || '---';
            }
            // Set persona name if available
            if (personaNames.gemini) {
                geminiPersonaEl.textContent = personaNames.gemini;
                geminiPersonaEl.style.display = '';
            } else {
                geminiPersonaEl.textContent = '';
                geminiPersonaEl.style.display = 'none';
            }
        } else {
            geminiDecisionBadgeEl.textContent = '---';
            geminiDecisionBadgeEl.className = 'ai-decision-badge';
            document.getElementById('detailGeminiReasoning').textContent = '---';
            geminiPersonaEl.textContent = '';
            geminiPersonaEl.style.display = 'none';
        }

        const chatgptDecisionBadgeEl = document.getElementById('detailChatGPTDecisionBadge');
        const chatgptPersonaEl = document.getElementById('detailChatGPTPersona');
        if (judgment.chatgpt) {
            if (judgment.chatgpt.failed) {
                chatgptDecisionBadgeEl.textContent = 'FAILED';
                chatgptDecisionBadgeEl.className = 'ai-decision-badge decision-rejected';
                document.getElementById('detailChatGPTReasoning').textContent =
                    judgment.chatgpt.raw_output || judgment.chatgpt.error || 'AI request failed';
            } else {
                chatgptDecisionBadgeEl.textContent = mapDecision(judgment.chatgpt.decision);
                chatgptDecisionBadgeEl.className = `ai-decision-badge ${DECISION_COLOR_MAP[judgment.chatgpt.decision] || ''}`;
                document.getElementById('detailChatGPTReasoning').textContent =
                    judgment.chatgpt.reasoning || judgment.chatgpt.reason || '---';
            }
            // Set persona name if available
            if (personaNames.chatgpt) {
                chatgptPersonaEl.textContent = personaNames.chatgpt;
                chatgptPersonaEl.style.display = '';
            } else {
                chatgptPersonaEl.textContent = '';
                chatgptPersonaEl.style.display = 'none';
            }
        } else {
            chatgptDecisionBadgeEl.textContent = '---';
            chatgptDecisionBadgeEl.className = 'ai-decision-badge';
            document.getElementById('detailChatGPTReasoning').textContent = '---';
            chatgptPersonaEl.textContent = '';
            chatgptPersonaEl.style.display = 'none';
        }

        // 重大度 (calculate severity_level if missing)
        const severityValue = judgment.judgment_severity || judgment.avg_severity || 0;
        const severityLevel = judgment.severity_level || getSeverityLevel(severityValue);
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
elements.seToggle.addEventListener('click', toggleSound);

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

// ============================================================
// Config Modal Event Listeners (v1.2)
// ============================================================

const DEFAULT_PERSONAS = {
    persona1: 'neutral_ai',
    persona2: 'neutral_ai',
    persona3: 'neutral_ai'
};

/**
 * Show config modal and load personas
 */
async function showConfigModal() {
    try {
        // Load personas from API
        const personas = await loadPersonas();

        // Store personas globally
        window.allPersonas = personas;

        // Initialize custom selects
        ['persona1', 'persona2', 'persona3'].forEach(selectId => {
            initCustomSelect(selectId, personas);
        });

        // Load current config from LocalStorage
        const config = loadConfig();
        setCustomSelectValue('persona1', config.persona1);
        setCustomSelectValue('persona2', config.persona2);
        setCustomSelectValue('persona3', config.persona3);

        // Show modal
        elements.configModal.classList.add('active');
    } catch (error) {
        console.error('Failed to load personas:', error);
        alert('ペルソナ読み込みに失敗しました: ' + error.message);
    }
}

/**
 * Initialize custom select with personas
 * @param {string} selectId - ID of the hidden input
 * @param {Array} personas - Persona list
 */
function initCustomSelect(selectId, personas) {
    const wrapper = document.querySelector(`[data-select-id="${selectId}"]`);
    if (!wrapper) return;

    const optionsContainer = wrapper.querySelector('.custom-select-options');
    const searchInput = wrapper.querySelector('.custom-select-search');
    const trigger = wrapper.querySelector('.custom-select-trigger');
    const valueDisplay = wrapper.querySelector('.custom-select-value');
    const hiddenInput = document.getElementById(selectId);

    // Check if already initialized
    if (wrapper.dataset.initialized === 'true') {
        // Just update options
        optionsContainer.innerHTML = personas.map(p =>
            `<div class="custom-select-option" data-value="${p.id}" data-name="${p.name}">${p.name}</div>`
        ).join('');
        return;
    }

    // Mark as initialized
    wrapper.dataset.initialized = 'true';

    // Populate options
    optionsContainer.innerHTML = personas.map(p =>
        `<div class="custom-select-option" data-value="${p.id}" data-name="${p.name}">${p.name}</div>`
    ).join('');

    // Toggle dropdown
    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        // Close other dropdowns
        document.querySelectorAll('.custom-select-wrapper.active').forEach(w => {
            if (w !== wrapper) w.classList.remove('active');
        });
        wrapper.classList.toggle('active');
        if (wrapper.classList.contains('active')) {
            searchInput.value = '';
            searchInput.focus();
            // Show all options
            optionsContainer.querySelectorAll('.custom-select-option').forEach(opt => {
                opt.classList.remove('hidden');
            });
        }
    });

    // Select option
    optionsContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('custom-select-option')) {
            const value = e.target.getAttribute('data-value');
            const name = e.target.getAttribute('data-name');

            // Update hidden input and display
            hiddenInput.value = value;
            valueDisplay.textContent = name;

            // Update selected state
            optionsContainer.querySelectorAll('.custom-select-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            e.target.classList.add('selected');

            // Close dropdown
            wrapper.classList.remove('active');
        }
    });

    // Search filter
    searchInput.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        optionsContainer.querySelectorAll('.custom-select-option').forEach(option => {
            const name = option.getAttribute('data-name').toLowerCase();
            if (name.includes(searchTerm)) {
                option.classList.remove('hidden');
            } else {
                option.classList.add('hidden');
            }
        });
    });

    // Prevent dropdown close when clicking search input
    searchInput.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

/**
 * Set custom select value
 * @param {string} selectId - ID of the hidden input
 * @param {string} value - Value to set
 */
function setCustomSelectValue(selectId, value) {
    const wrapper = document.querySelector(`[data-select-id="${selectId}"]`);
    if (!wrapper) return;

    const hiddenInput = document.getElementById(selectId);
    const valueDisplay = wrapper.querySelector('.custom-select-value');
    const optionsContainer = wrapper.querySelector('.custom-select-options');

    hiddenInput.value = value;

    // Find and display selected option
    const selectedOption = optionsContainer.querySelector(`[data-value="${value}"]`);
    if (selectedOption) {
        valueDisplay.textContent = selectedOption.getAttribute('data-name');
        optionsContainer.querySelectorAll('.custom-select-option').forEach(opt => {
            opt.classList.remove('selected');
        });
        selectedOption.classList.add('selected');
    } else if (window.allPersonas) {
        // Fallback: find name from allPersonas
        const persona = window.allPersonas.find(p => p.id === value);
        if (persona) {
            valueDisplay.textContent = persona.name;
        }
    }
}

/**
 * Save config to LocalStorage (v1.2)
 * @returns {Object} - Saved config
 */
function saveConfig() {
    const config = {
        persona1: elements.persona1.value,
        persona2: elements.persona2.value,
        persona3: elements.persona3.value
    };

    try {
        localStorage.setItem('magin_ai_config', JSON.stringify(config));
        return config;
    } catch (error) {
        console.warn('LocalStorage unavailable, config not persisted:', error);
        return config; // Still return for session use
    }
}

/**
 * Load config from LocalStorage (v1.2)
 * @returns {Object} - Config object
 */
function loadConfig() {
    try {
        const stored = localStorage.getItem('magin_ai_config');
        if (stored) {
            const config = JSON.parse(stored);
            return config;
        }
    } catch (error) {
        console.warn('LocalStorage unavailable, using defaults:', error);
    }

    // Return defaults if no stored config
    console.log('Using default config:', DEFAULT_PERSONAS);
    return DEFAULT_PERSONAS;
}

/**
 * Get persona names from config
 * @returns {Object} - Persona names {claude, gemini, chatgpt}
 */
function getPersonaNames() {
    const config = loadConfig();

    // Find persona names from allPersonas if available
    if (window.allPersonas) {
        const findName = (id) => {
            const persona = window.allPersonas.find(p => p.id === id);
            return persona ? persona.name : id;
        };

        return {
            claude: findName(config.persona1),
            gemini: findName(config.persona2),
            chatgpt: findName(config.persona3)
        };
    }

    // Fallback to IDs
    return {
        claude: config.persona1,
        gemini: config.persona2,
        chatgpt: config.persona3
    };
}

/**
 * Reset config to defaults (v1.2)
 */
function resetConfig() {
    try {
        localStorage.removeItem('magin_ai_config');
        console.log('Config reset to defaults');
    } catch (error) {
        console.warn('LocalStorage unavailable:', error);
    }

    // Update UI
    setCustomSelectValue('persona1', DEFAULT_PERSONAS.persona1);
    setCustomSelectValue('persona2', DEFAULT_PERSONAS.persona2);
    setCustomSelectValue('persona3', DEFAULT_PERSONAS.persona3);
}

// ============================================================
// v1.3 CONFIG Modal (Task 3.2.2 - 3.3.3)
// ============================================================

/**
 * Open CONFIG modal with 2-tab structure (v1.3 Task 3.2.2)
 */
async function openConfigModal() {
    try {
        // Show loading
        showToast('Loading configuration...', 'info');

        // Fetch config and personas
        const [configResponse, personasResponse] = await Promise.all([
            fetch(`${API_BASE_URL}/api/config`),
            fetch(`${API_BASE_URL}/api/personas`)
        ]);

        if (!configResponse.ok || !personasResponse.ok) {
            throw new Error('Failed to load configuration');
        }

        const backendConfig = await configResponse.json();
        const { personas } = await personasResponse.json();

        // Convert backend format to frontend format
        const config = convertBackendToFrontendConfig(backendConfig);

        // Store globally
        window.currentConfig = config;
        window.allPersonas = personas;

        // Create modal dynamically
        createConfigModalV3();

        // Populate PERSONA CONFIG tab
        populatePersonaConfig(config, personas);

        // Populate NODE CONFIG tab
        populateNodeConfig(config);

        // Show modal
        const modal = document.getElementById('configModalV3');
        modal.classList.add('active');

        // Set active tab to PERSONA CONFIG
        switchConfigTab('persona');

    } catch (error) {
        console.error('Failed to open config modal:', error);
        showToast('Failed to load configuration', 'error');
    }
}

/**
 * Create CONFIG modal HTML structure (v1.3)
 */
function createConfigModalV3() {
    // Remove existing modal if present
    const existing = document.getElementById('configModalV3');
    if (existing) {
        existing.remove();
    }

    const modalHTML = `
        <div class="modal" id="configModalV3">
            <div class="modal-content" style="max-width: 900px;">
                <button class="modal-close" onclick="closeConfigModal()">×</button>
                <h2>SYSTEM CONFIGURATION</h2>

                <!-- Tab Headers -->
                <div class="tab-headers">
                    <div class="tab-header active" data-tab="persona">PERSONA CONFIG</div>
                    <div class="tab-header" data-tab="node">NODE CONFIG</div>
                </div>

                <!-- Tab Content: PERSONA CONFIG -->
                <div class="tab-content active" id="tab-persona">
                    <div class="detail-section">
                        <div class="detail-label">DESCRIPTION</div>
                        <div class="detail-value" style="font-size: 13px; color: #ccc;">
                            各NODEに割り当てるペルソナを選択してください。ENGINE/MODEL設定はNODE CONFIGタブで行います。
                        </div>
                    </div>
                    <div id="personaConfigContent"></div>
                </div>

                <!-- Tab Content: NODE CONFIG -->
                <div class="tab-content" id="tab-node">
                    <div class="detail-section">
                        <div class="detail-label">DESCRIPTION</div>
                        <div class="detail-value" style="font-size: 13px; color: #ccc;">
                            各NODEのENGINEとMODELを設定してください。
                        </div>
                    </div>

                    <!-- Sub-tab Headers -->
                    <div class="sub-tab-headers">
                        <div class="sub-tab-header active" data-subtab="node1">NODE 1</div>
                        <div class="sub-tab-header" data-subtab="node2">NODE 2</div>
                        <div class="sub-tab-header" data-subtab="node3">NODE 3</div>
                    </div>

                    <!-- Sub-tab Contents -->
                    <div id="nodeConfigContent"></div>
                </div>

                <!-- Action Buttons -->
                <div class="config-buttons">
                    <button class="btn" onclick="saveConfigV3()">SAVE</button>
                    <button class="btn btn-secondary" onclick="closeConfigModal()">CANCEL</button>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);

    // Attach tab switching event listeners
    document.querySelectorAll('#configModalV3 .tab-header').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.getAttribute('data-tab');
            switchConfigTab(tabName);
        });
    });

    // Attach sub-tab switching event listeners
    document.querySelectorAll('#configModalV3 .sub-tab-header').forEach(subtab => {
        subtab.addEventListener('click', () => {
            const subtabName = subtab.getAttribute('data-subtab');
            switchNodeSubTab(subtabName);
        });
    });
}

/**
 * Switch between PERSONA CONFIG and NODE CONFIG tabs (v1.3)
 * @param {string} tabName - 'persona' or 'node'
 */
function switchConfigTab(tabName) {
    // Update tab headers
    document.querySelectorAll('#configModalV3 .tab-header').forEach(tab => {
        tab.classList.toggle('active', tab.getAttribute('data-tab') === tabName);
    });

    // Update tab contents
    document.querySelectorAll('#configModalV3 .tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `tab-${tabName}`);
    });
}

/**
 * Switch between NODE sub-tabs (v1.3)
 * @param {string} subtabName - 'node1', 'node2', or 'node3'
 */
function switchNodeSubTab(subtabName) {
    // Update sub-tab headers
    document.querySelectorAll('#configModalV3 .sub-tab-header').forEach(subtab => {
        subtab.classList.toggle('active', subtab.getAttribute('data-subtab') === subtabName);
    });

    // Update sub-tab contents
    document.querySelectorAll('#configModalV3 .sub-tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `subtab-${subtabName}`);
    });
}

/**
 * Populate PERSONA CONFIG tab (v1.3 Task 3.2.3)
 * @param {Object} config - Current configuration
 * @param {Array} personas - Persona list
 */
function populatePersonaConfig(config, personas) {
    const container = document.getElementById('personaConfigContent');
    const nodes = [
        { id: 'node1', label: 'NODE 1', config: config.node1 },
        { id: 'node2', label: 'NODE 2', config: config.node2 },
        { id: 'node3', label: 'NODE 3', config: config.node3 }
    ];

    let html = '';
    nodes.forEach(node => {
        const engineModel = node.config.model
            ? `${node.config.engine}: ${node.config.model}`
            : node.config.engine;

        html += `
            <div class="detail-section">
                <div class="detail-label">${node.label} (${engineModel})</div>
                <div class="custom-select-wrapper" data-select-id="${node.id}_persona">
                    <div class="custom-select-trigger">
                        <span class="custom-select-value">Loading...</span>
                        <span class="custom-select-arrow">▼</span>
                    </div>
                    <div class="custom-select-dropdown">
                        <input type="text" class="custom-select-search" placeholder="Search persona...">
                        <div class="custom-select-options"></div>
                    </div>
                    <input type="hidden" id="${node.id}_persona" value="${node.config.persona_id}">
                </div>
            </div>
        `;
    });

    container.innerHTML = html;

    // Initialize custom selects
    nodes.forEach(node => {
        initCustomSelectV3(`${node.id}_persona`, personas, node.config.persona_id);
    });
}

/**
 * Populate NODE CONFIG tab (v1.3 Task 3.3.1)
 * @param {Object} config - Current configuration
 */
function populateNodeConfig(config) {
    const container = document.getElementById('nodeConfigContent');
    const nodes = ['node1', 'node2', 'node3'];

    const engineOptions = [
        'Claude',
        'Gemini',
        'ChatGPT',
        'API_Gemini',
        'API_OpenRouter',
        'API_Ollama'
    ];

    const modelsByEngine = {
        'API_Gemini': ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro'],
        'API_OpenRouter': [
            'x-ai/grok-code-fast-1',
            'anthropic/claude-sonnet-4.5',
            'openai/gpt-oss-20b:free',
            'google/gemma-3-27b-it:free'
        ],
        'API_Ollama': ['gemma3:12b', 'gemma3:27b', 'gpt-oss:latest']
    };

    let html = '';
    nodes.forEach(nodeId => {
        const nodeConfig = config[nodeId];
        const nodeLabel = nodeId.toUpperCase().replace('NODE', 'NODE ');

        html += `
            <div class="sub-tab-content ${nodeId === 'node1' ? 'active' : ''}" id="subtab-${nodeId}">
                <div class="detail-section">
                    <div class="detail-label">ENGINE</div>
                    <select id="${nodeId}_engine" class="config-select">
                        ${engineOptions.map(e => `<option value="${e}" ${e === nodeConfig.engine ? 'selected' : ''}>${e}</option>`).join('')}
                    </select>
                    <div id="${nodeId}_engine_info" class="engine-info" style="margin-top: 10px; font-size: 12px; color: #888; line-height: 1.6;"></div>
                </div>
                <div class="detail-section" id="${nodeId}_model_section" style="display: ${nodeConfig.model ? 'block' : 'none'};">
                    <div class="detail-label">MODEL</div>
                    <select id="${nodeId}_model" class="config-select">
                        <option value="">-- Select Model --</option>
                    </select>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;

    // Attach engine change listeners
    nodes.forEach(nodeId => {
        const engineSelect = document.getElementById(`${nodeId}_engine`);
        const modelSection = document.getElementById(`${nodeId}_model_section`);
        const modelSelect = document.getElementById(`${nodeId}_model`);
        const engineInfo = document.getElementById(`${nodeId}_engine_info`);

        // Update engine info display
        const updateEngineInfo = (engine) => {
            const infoMap = {
                'Claude': 'Claude Codeがインストールされ、利用設定済みであることが必要です(有料プラン加入必要)',
                'Gemini': 'Gemini CLIがインストールされ、利用設定済みであることが必要です',
                'ChatGPT': 'Codex CLIがインストールされ、利用設定済みであることが必要です(有料プラン加入必要)',
                'API_Gemini': 'Gemini API利用できるAPIキーを取得し、API SETTINGにキーの設定が必要です',
                'API_OpenRouter': 'OpenRouterが利用できるAPIキーを取得し、API SETTINGにキーの設定が必要です(有料)',
                'API_Ollama': 'Ollamaサーバを構築し、対応モデルをダウンロードの上、API SETTINGにエンドポイントURLの設定が必要です'
            };
            engineInfo.textContent = infoMap[engine] || '';
        };

        // Initial info display
        updateEngineInfo(engineSelect.value);

        engineSelect.addEventListener('change', () => {
            const selectedEngine = engineSelect.value;
            const isCLI = ['Claude', 'Gemini', 'ChatGPT'].includes(selectedEngine);

            // Update info
            updateEngineInfo(selectedEngine);

            if (isCLI) {
                // Hide model selection for CLI engines
                modelSection.style.display = 'none';
                modelSelect.value = '';
            } else {
                // Show model selection
                modelSection.style.display = 'block';

                // Populate models
                const models = modelsByEngine[selectedEngine] || [];
                modelSelect.innerHTML = '<option value="">-- Select Model --</option>' +
                    models.map(m => `<option value="${m}">${m}</option>`).join('');
            }

            // Update PERSONA CONFIG tab display (Task 3.3.2)
            updatePersonaConfigDisplay();
        });

        // Initialize model dropdown
        const currentEngine = config[nodeId].engine;
        const isCLI = ['Claude', 'Gemini', 'ChatGPT'].includes(currentEngine);

        if (!isCLI && modelsByEngine[currentEngine]) {
            const models = modelsByEngine[currentEngine];
            modelSelect.innerHTML = '<option value="">-- Select Model --</option>' +
                models.map(m => `<option value="${m}" ${m === config[nodeId].model ? 'selected' : ''}>${m}</option>`).join('');
        }
    });
}

/**
 * Update PERSONA CONFIG tab Engine/Model display (v1.3 Task 3.3.2)
 */
function updatePersonaConfigDisplay() {
    const nodes = ['node1', 'node2', 'node3'];

    nodes.forEach((nodeId, index) => {
        const engineSelect = document.getElementById(`${nodeId}_engine`);
        const modelSelect = document.getElementById(`${nodeId}_model`);

        if (!engineSelect) return;

        const engine = engineSelect.value;
        const model = modelSelect ? modelSelect.value : '';

        const engineModel = model ? `${engine}: ${model}` : engine;

        // Update label in PERSONA CONFIG tab
        const labels = document.querySelectorAll('#tab-persona .detail-label');
        if (labels[index + 1]) { // +1 to skip DESCRIPTION label
            const nodeLabel = `NODE ${index + 1} (${engineModel})`;
            labels[index + 1].textContent = nodeLabel;
        }
    });
}

/**
 * Initialize custom select for personas (v1.3)
 * @param {string} selectId - ID of the hidden input
 * @param {Array} personas - Persona list
 * @param {string} selectedValue - Initially selected value
 */
function initCustomSelectV3(selectId, personas, selectedValue) {
    const wrapper = document.querySelector(`[data-select-id="${selectId}"]`);
    if (!wrapper) return;

    const optionsContainer = wrapper.querySelector('.custom-select-options');
    const searchInput = wrapper.querySelector('.custom-select-search');
    const trigger = wrapper.querySelector('.custom-select-trigger');
    const valueDisplay = wrapper.querySelector('.custom-select-value');
    const hiddenInput = document.getElementById(selectId);

    // Populate options
    optionsContainer.innerHTML = personas.map(p =>
        `<div class="custom-select-option ${p.id === selectedValue ? 'selected' : ''}" data-value="${p.id}" data-name="${p.name}">${p.name}</div>`
    ).join('');

    // Set initial display
    const selectedPersona = personas.find(p => p.id === selectedValue);
    if (selectedPersona) {
        valueDisplay.textContent = selectedPersona.name;
        hiddenInput.value = selectedValue;
    }

    // Toggle dropdown
    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        // Close other dropdowns
        document.querySelectorAll('.custom-select-wrapper.active').forEach(w => {
            if (w !== wrapper) w.classList.remove('active');
        });
        wrapper.classList.toggle('active');
        if (wrapper.classList.contains('active')) {
            searchInput.value = '';
            searchInput.focus();
            // Show all options
            optionsContainer.querySelectorAll('.custom-select-option').forEach(opt => {
                opt.classList.remove('hidden');
            });
        }
    });

    // Select option
    optionsContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('custom-select-option')) {
            const value = e.target.getAttribute('data-value');
            const name = e.target.getAttribute('data-name');

            hiddenInput.value = value;
            valueDisplay.textContent = name;

            optionsContainer.querySelectorAll('.custom-select-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            e.target.classList.add('selected');

            wrapper.classList.remove('active');
        }
    });

    // Search filter
    searchInput.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        optionsContainer.querySelectorAll('.custom-select-option').forEach(option => {
            const name = option.getAttribute('data-name').toLowerCase();
            option.classList.toggle('hidden', !name.includes(searchTerm));
        });
    });

    // Prevent dropdown close when clicking search input
    searchInput.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

/**
 * Get current config from UI (v1.3)
 * @returns {Object} - Configuration object
 */
function getCurrentConfigFromUI() {
    return {
        node1: {
            engine: document.getElementById('node1_engine').value,
            model: document.getElementById('node1_model').value || null,
            persona_id: document.getElementById('node1_persona').value
        },
        node2: {
            engine: document.getElementById('node2_engine').value,
            model: document.getElementById('node2_model').value || null,
            persona_id: document.getElementById('node2_persona').value
        },
        node3: {
            engine: document.getElementById('node3_engine').value,
            model: document.getElementById('node3_model').value || null,
            persona_id: document.getElementById('node3_persona').value
        }
    };
}

/**
 * Save configuration (v1.3 Task 3.3.3)
 */
async function saveConfigV3() {
    try {
        // Show loading
        showToast('Saving configuration...', 'info');

        // Get current config from UI
        const config = getCurrentConfigFromUI();

        // Validate
        const nodes = ['node1', 'node2', 'node3'];
        for (const nodeId of nodes) {
            const nodeConfig = config[nodeId];
            const isCLI = ['Claude', 'Gemini', 'ChatGPT'].includes(nodeConfig.engine);

            if (!isCLI && !nodeConfig.model) {
                showToast(`Please select a model for ${nodeId.toUpperCase()}`, 'error');
                return;
            }

            if (!nodeConfig.persona_id) {
                showToast(`Please select a persona for ${nodeId.toUpperCase()}`, 'error');
                return;
            }
        }

        // Convert to backend format and save
        const backendConfig = convertFrontendToBackendConfig(config);
        const response = await fetch(`${API_BASE_URL}/api/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(backendConfig)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to save configuration');
        }

        // Save to LocalStorage
        saveUserConfig(config);

        // Update NODE display
        updateNodeDisplay();

        // Show success message
        showToast('Configuration saved successfully', 'success');

        // Close modal
        closeConfigModal();

    } catch (error) {
        console.error('Failed to save config:', error);
        showToast(error.message, 'error');
    }
}

/**
 * Close CONFIG modal (v1.3)
 */
function closeConfigModal() {
    const modal = document.getElementById('configModalV3');
    if (modal) {
        modal.classList.remove('active');
    }

    // Close custom select dropdowns
    document.querySelectorAll('.custom-select-wrapper.active').forEach(wrapper => {
        wrapper.classList.remove('active');
    });
}

/**
 * Show toast notification (v1.3)
 * @param {string} message - Toast message
 * @param {string} type - 'info', 'success', or 'error'
 */
function showToast(message, type = 'info') {
    // Remove existing toast
    const existing = document.getElementById('toast');
    if (existing) {
        existing.remove();
    }

    // Create toast
    const toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    document.body.appendChild(toast);

    // Show toast
    setTimeout(() => {
        toast.classList.add('active');
    }, 10);

    // Hide and remove after 3 seconds
    setTimeout(() => {
        toast.classList.remove('active');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

// ============================================================
// v1.3 API SETTING Modal (Task 3.4.1-3.4.2)
// ============================================================

/**
 * Open API SETTING modal (v1.3 Task 3.4.2)
 */
async function openApiSettingModal() {
    // Create modal dynamically
    createApiSettingModal();

    // Load current API settings
    try {
        const response = await fetch(`${API_BASE_URL}/api/env`);
        if (response.ok) {
            const env = await response.json();

            // Display masked keys (show ●●●●●●●● if key exists)
            const geminiInput = document.getElementById('geminiApiKey');
            const openrouterInput = document.getElementById('openrouterApiKey');
            const ollamaInput = document.getElementById('ollamaUrl');

            // env.GEMINI_API_KEY is boolean
            if (env.GEMINI_API_KEY === true) {
                geminiInput.value = '●●●●●●●●';
                geminiInput.dataset.hasKey = 'true';
            }
            // env.OPENROUTER_API_KEY is boolean
            if (env.OPENROUTER_API_KEY === true) {
                openrouterInput.value = '●●●●●●●●';
                openrouterInput.dataset.hasKey = 'true';
            }
            // env.OLLAMA_URL is string
            if (env.OLLAMA_URL) {
                ollamaInput.value = env.OLLAMA_URL;
            }
        }
    } catch (error) {
        console.error('Failed to load API settings:', error);
    }

    // Show modal
    const modal = document.getElementById('apiSettingModal');
    modal.classList.add('active');
}

/**
 * Create API SETTING modal HTML structure (v1.3)
 */
function createApiSettingModal() {
    // Remove existing modal if present
    const existing = document.getElementById('apiSettingModal');
    if (existing) {
        existing.remove();
    }

    const modalHTML = `
        <div class="modal" id="apiSettingModal">
            <div class="modal-content" style="max-width: 600px;">
                <button class="modal-close" onclick="closeApiSettingModal()">×</button>
                <h2>API SETTINGS</h2>

                <!-- Security Warning -->
                <div class="detail-section" style="background: rgba(255, 0, 0, 0.1); border-left: 3px solid #f44336; padding: 15px;">
                    <div class="detail-label" style="color: #f44336;">⚠️ SECURITY WARNING</div>
                    <div class="detail-value" style="font-size: 13px; color: #ff5555;">
                        APIキーは平文で保存されます。ローカル環境でのみ使用してください。
                    </div>
                </div>

                <!-- Gemini API Key -->
                <div class="detail-section">
                    <div class="detail-label">GEMINI API KEY</div>
                    <input type="password" id="geminiApiKey" class="config-input" placeholder="Enter Gemini API Key" onfocus="clearMaskedInput(this)">
                </div>

                <!-- OpenRouter API Key -->
                <div class="detail-section">
                    <div class="detail-label">OPENROUTER API KEY</div>
                    <input type="password" id="openrouterApiKey" class="config-input" placeholder="Enter OpenRouter API Key" onfocus="clearMaskedInput(this)">
                </div>

                <!-- Ollama URL -->
                <div class="detail-section">
                    <div class="detail-label">OLLAMA URL</div>
                    <input type="text" id="ollamaUrl" class="config-input" placeholder="http://localhost:11434" value="http://localhost:11434">
                </div>

                <!-- Action Buttons -->
                <div class="config-buttons">
                    <button class="btn" onclick="saveApiSettings()">SAVE</button>
                    <button class="btn btn-secondary" onclick="closeApiSettingModal()">CANCEL</button>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

/**
 * Clear masked input on focus (v1.3)
 */
function clearMaskedInput(input) {
    if (input.dataset.hasKey === 'true' && input.value === '●●●●●●●●') {
        input.value = '';
        input.dataset.hasKey = 'false';
    }
}

/**
 * Validate API key format (v1.3)
 */
function validateApiKey(key, type) {
    if (type === 'gemini') {
        // Gemini API keys start with "AIza" and are typically 39 characters
        if (!key.startsWith('AIza')) {
            return 'Gemini API key must start with "AIza"';
        }
        if (key.length !== 39) {
            return `Gemini API key should be 39 characters (current: ${key.length})`;
        }
    } else if (type === 'openrouter') {
        // OpenRouter API keys start with "sk-or-v1-"
        if (!key.startsWith('sk-or-v1-')) {
            return 'OpenRouter API key must start with "sk-or-v1-"';
        }
    }
    return null; // Valid
}

/**
 * Save API settings (v1.3 Task 3.4.2)
 */
async function saveApiSettings() {
    try {
        // Show loading
        showToast('Saving API settings...', 'info');

        // Get values
        const geminiApiKey = document.getElementById('geminiApiKey').value.trim();
        const openrouterApiKey = document.getElementById('openrouterApiKey').value.trim();
        const ollamaUrl = document.getElementById('ollamaUrl').value.trim();

        // Validate API keys (skip masked values)
        if (geminiApiKey && geminiApiKey !== '●●●●●●●●') {
            const error = validateApiKey(geminiApiKey, 'gemini');
            if (error) {
                showToast(error, 'error');
                return;
            }
        }

        if (openrouterApiKey && openrouterApiKey !== '●●●●●●●●') {
            const error = validateApiKey(openrouterApiKey, 'openrouter');
            if (error) {
                showToast(error, 'error');
                return;
            }
        }

        // Prepare payload (skip masked values - keep existing keys)
        const payload = {};

        // Only include in payload if user actually changed the value
        if (geminiApiKey && geminiApiKey !== '●●●●●●●●') {
            payload.GEMINI_API_KEY = geminiApiKey;
        }
        if (openrouterApiKey && openrouterApiKey !== '●●●●●●●●') {
            payload.OPENROUTER_API_KEY = openrouterApiKey;
        }
        if (ollamaUrl) {
            payload.OLLAMA_URL = ollamaUrl;
        }

        // If all fields are masked (unchanged), nothing to save
        if (Object.keys(payload).length === 0) {
            showToast('No changes to save', 'info');
            closeApiSettingModal();
            return;
        }

        // Save to backend
        const response = await fetch(`${API_BASE_URL}/api/save-env`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to save API settings');
        }

        // Show success message
        showToast('API settings saved successfully', 'success');

        // Close modal
        closeApiSettingModal();

    } catch (error) {
        console.error('Failed to save API settings:', error);
        showToast(error.message, 'error');
    }
}

/**
 * Close API SETTING modal (v1.3)
 */
function closeApiSettingModal() {
    const modal = document.getElementById('apiSettingModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// ============================================================
// v1.3 TEST Function (Task 3.5.1-3.5.3)
// ============================================================

/**
 * Test connections with paid model warning (v1.3 Task 3.5.2 + 3.5.3)
 */
async function testConnections() {
    try {
        // Load config
        const config = loadUserConfig();

        // Check for API engines (excluding Ollama which is local)
        const apiEngines = ['API_Gemini', 'API_OpenRouter'];
        const hasApiEngine = [config.node1, config.node2, config.node3].some(node =>
            apiEngines.includes(node.engine)
        );

        if (hasApiEngine) {
            const confirmed = confirm('テストでは実際のAPIリクエストが送信されます。設定によっては料金が発生する可能性があります。\n\n続行しますか？');
            if (!confirmed) {
                return;
            }
        }

        // Show loading modal immediately
        createTestLoadingModal();

        // Convert to backend format and call test endpoint
        const backendConfig = convertFrontendToBackendConfig(config);
        const response = await fetch(`${API_BASE_URL}/api/test-connections`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(backendConfig)
        });

        if (!response.ok) {
            closeTestLoadingModal();
            throw new Error('Test failed');
        }

        const results = await response.json();

        // Close loading modal and show results
        closeTestLoadingModal();
        showTestResultsModal(results);

    } catch (error) {
        console.error('Test failed:', error);
        showToast('Test failed: ' + error.message, 'error');
    }
}

/**
 * Show test results modal (v1.3 Task 3.5.3)
 * @param {Object} results - Test results
 */
function showTestResultsModal(results) {
    // Create modal dynamically
    createTestResultsModal(results);

    // Show modal
    const modal = document.getElementById('testResultsModal');
    modal.classList.add('active');
}

/**
 * Create test results modal HTML structure (v1.3)
 * @param {Object} results - Test results
 */
function createTestResultsModal(results) {
    // Remove existing modal if present
    const existing = document.getElementById('testResultsModal');
    if (existing) {
        existing.remove();
    }

    // Backend returns: {"results": [{node_id: 1, engine: "...", model: "...", status: "ok"|"error", response_time_ms: number, error: string|null}, ...]}
    let tableRows = '';

    results.results.forEach((result) => {
        const nodeLabel = `NODE ${result.node_id}`;
        const engine = result.engine || '---';
        const model = result.model || 'N/A';
        const status = result.status === 'ok' ? 'OK' : 'Error';
        const statusClass = result.status === 'ok' ? 'status-ok' : 'status-error';
        const responseTime = result.response_time_ms ? `${(result.response_time_ms / 1000).toFixed(2)}s` : '---';
        const error = result.error || '---';

        tableRows += `
            <tr>
                <td>${nodeLabel}</td>
                <td>${engine}</td>
                <td>${model}</td>
                <td class="${statusClass}">${status}</td>
                <td>${responseTime}</td>
                <td>${error}</td>
            </tr>
        `;
    });

    const modalHTML = `
        <div class="modal" id="testResultsModal">
            <div class="modal-content" style="max-width: 1000px;">
                <button class="modal-close" onclick="closeTestResultsModal()">×</button>
                <h2>CONNECTION TEST RESULTS</h2>

                <table class="test-results-table">
                    <thead>
                        <tr>
                            <th>NODE</th>
                            <th>ENGINE</th>
                            <th>MODEL</th>
                            <th>STATUS</th>
                            <th>RESPONSE TIME</th>
                            <th>ERROR</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}
                    </tbody>
                </table>

                <div class="config-buttons">
                    <button class="btn" onclick="closeTestResultsModal()">CLOSE</button>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

/**
 * Close test results modal (v1.3)
 */
function closeTestResultsModal() {
    const modal = document.getElementById('testResultsModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

/**
 * Create test loading modal (v1.3)
 */
function createTestLoadingModal() {
    // Remove existing modal if present
    const existing = document.getElementById('testLoadingModal');
    if (existing) {
        existing.remove();
    }

    const modalHTML = `
        <div class="modal active" id="testLoadingModal">
            <div class="modal-content" style="max-width: 500px; text-align: center;">
                <h2>CONNECTION TEST</h2>
                <div style="padding: 40px 20px;">
                    <div class="spinner" style="margin: 0 auto 20px;"></div>
                    <p style="font-size: 16px; color: #00ff00;">Testing connections...</p>
                    <p style="font-size: 13px; color: #888; margin-top: 10px;">Please wait while we verify all nodes.</p>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

/**
 * Close test loading modal (v1.3)
 */
function closeTestLoadingModal() {
    const modal = document.getElementById('testLoadingModal');
    if (modal) {
        modal.remove();
    }
}

// Config button click (v1.3 - use new modal)
elements.configBtn.addEventListener('click', openConfigModal);

// API SETTING button click (v1.3)
document.getElementById('apiSettingBtn').addEventListener('click', openApiSettingModal);

// TEST button click (v1.3)
document.getElementById('testBtn').addEventListener('click', testConnections);

// Close custom selects when clicking outside
document.addEventListener('click', () => {
    document.querySelectorAll('.custom-select-wrapper.active').forEach(wrapper => {
        wrapper.classList.remove('active');
    });
});

// Close config modal
elements.closeConfigModal.addEventListener('click', () => {
    elements.configModal.classList.remove('active');
});

// Save config button
elements.saveConfigBtn.addEventListener('click', () => {
    saveConfig();
    elements.configModal.classList.remove('active');
    // Removed alert - just close modal on success
});

// Reset config button
elements.resetConfigBtn.addEventListener('click', () => {
    if (confirm('設定をデフォルトに戻しますか？')) {
        resetConfig();
        alert('設定をデフォルトに戻しました');
    }
});

// Copy summary button (v1.2)
document.getElementById('copySummaryBtn').addEventListener('click', async () => {
    await copySummary();
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

// ========================================
// HEXAGON GRID GENERATION (v1.1)
// ========================================

/**
 * Generate hexagon grid background
 */
function generateHexagonGrid() {
    const container = document.getElementById('hexagonBg');
    if (!container) return;

    const hexWidth = 60;
    const hexHeight = 52; // Actual vertical spacing
    const cols = Math.ceil(window.innerWidth / hexWidth) + 2;
    const rows = Math.ceil(window.innerHeight / hexHeight) + 2;

    for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
            const hex = document.createElement('div');
            hex.className = 'hexagon';

            // Offset every other row
            const offsetX = (row % 2) * (hexWidth / 2);
            const x = col * hexWidth + offsetX;
            const y = row * hexHeight;

            hex.style.left = `${x}px`;
            hex.style.top = `${y}px`;

            container.appendChild(hex);
        }
    }
}

// ========================================
// Triangle Link Effect (v1.1)
// ========================================
function triggerTriangleLink() {
    const wrapper = document.getElementById('magi-system-wrapper');
    if (!wrapper) return;

    // Create triangle container
    const container = document.createElement('div');
    container.className = 'triangle-container';
    container.style.position = 'absolute';
    container.style.top = '0';
    container.style.left = '0';
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.pointerEvents = 'none';
    container.style.zIndex = '5';
    wrapper.appendChild(container);

    // Get AI unit positions
    const gemini = document.getElementById('gemini');
    const claude = document.getElementById('claude');
    const chatgpt = document.getElementById('chatgpt');

    const getCenter = (el) => {
        const rect = el.getBoundingClientRect();
        const parentRect = wrapper.getBoundingClientRect();
        return {
            x: rect.left + rect.width / 2 - parentRect.left,
            y: rect.top + rect.height / 2 - parentRect.top
        };
    };

    const geminiPos = getCenter(gemini);
    const claudePos = getCenter(claude);
    const chatgptPos = getCenter(chatgpt);

    // Draw lines in sequence (faster timing)
    const lines = [
        { from: claudePos, to: geminiPos, delay: 0 },
        { from: geminiPos, to: chatgptPos, delay: 150 },
        { from: chatgptPos, to: claudePos, delay: 300 }
    ];

    lines.forEach(({ from, to, delay }) => {
        setTimeout(() => {
            const line = document.createElement('div');
            line.className = 'triangle-line';

            const dx = to.x - from.x;
            const dy = to.y - from.y;
            const length = Math.sqrt(dx * dx + dy * dy);
            const angle = Math.atan2(dy, dx) * 180 / Math.PI;

            line.style.position = 'absolute';
            line.style.left = `${from.x}px`;
            line.style.top = `${from.y}px`;
            line.style.width = '0';
            line.style.height = '3px';
            line.style.background = 'linear-gradient(90deg, #ff6b00, #00e0e0)';
            line.style.transformOrigin = '0 0';
            line.style.transform = `rotate(${angle}deg)`;
            line.style.boxShadow = '0 0 10px rgba(255, 107, 0, 0.8)';

            container.appendChild(line);

            // Animate line drawing
            setTimeout(() => {
                line.style.transition = 'width 0.2s ease-out';
                line.style.width = `${length}px`;
            }, 10);
        }, delay);
    });

    // Fade out after breathing time
    setTimeout(() => {
        container.style.transition = 'opacity 0.3s ease-out';
        container.style.opacity = '0';

        // Remove after fade out
        setTimeout(() => {
            container.remove();
        }, 300);
    }, 800); // Start fade at 800ms (300ms delay + 200ms animation + 300ms display)
}

// ============================================================
// v1.3 Configuration Management
// ============================================================

/**
 * Initialize configuration on page load (v1.3 Task 3.1.1)
 * Loads config from backend and syncs with LocalStorage
 */
async function initializeConfig() {
    try {
        // Fetch configuration from backend
        const response = await fetch(`${API_BASE_URL}/api/config`);
        if (!response.ok) {
            console.warn('Failed to load config from backend, using LocalStorage defaults');
            return;
        }

        const backendData = await response.json();

        // Convert backend format (nodes array) to frontend format (node1/node2/node3)
        const backendConfig = convertBackendToFrontendConfig(backendData);

        // Load current LocalStorage config
        const localConfig = loadUserConfig();

        // Check if configs match
        const configsMatch =
            localConfig.node1.engine === backendConfig.node1.engine &&
            localConfig.node1.model === backendConfig.node1.model &&
            localConfig.node1.persona_id === backendConfig.node1.persona_id &&
            localConfig.node2.engine === backendConfig.node2.engine &&
            localConfig.node2.model === backendConfig.node2.model &&
            localConfig.node2.persona_id === backendConfig.node2.persona_id &&
            localConfig.node3.engine === backendConfig.node3.engine &&
            localConfig.node3.model === backendConfig.node3.model &&
            localConfig.node3.persona_id === backendConfig.node3.persona_id;

        if (!configsMatch) {
            // Mismatch: backend takes precedence
            console.log('Config mismatch detected. Using backend config.');
            saveUserConfig(backendConfig);
        }
    } catch (error) {
        console.error('Failed to initialize config:', error);
    }
}

/**
 * Convert backend config format to frontend format
 * Backend: { nodes: [{id, name, engine, model, persona_id}, ...] }
 * Frontend: { node1: {engine, model, persona_id}, node2: {...}, node3: {...} }
 */
function convertBackendToFrontendConfig(backendData) {
    if (!backendData.nodes || backendData.nodes.length !== 3) {
        console.warn('Invalid backend config format, using defaults');
        return loadUserConfig();
    }

    return {
        node1: {
            engine: backendData.nodes[0].engine,
            model: backendData.nodes[0].model,
            persona_id: backendData.nodes[0].persona_id
        },
        node2: {
            engine: backendData.nodes[1].engine,
            model: backendData.nodes[1].model,
            persona_id: backendData.nodes[1].persona_id
        },
        node3: {
            engine: backendData.nodes[2].engine,
            model: backendData.nodes[2].model,
            persona_id: backendData.nodes[2].persona_id
        }
    };
}

/**
 * Convert frontend config format to backend format
 * Frontend: { node1: {engine, model, persona_id}, node2: {...}, node3: {...} }
 * Backend: { nodes: [{id, name, engine, model, persona_id}, ...] }
 */
function convertFrontendToBackendConfig(frontendConfig) {
    return {
        nodes: [
            {
                id: 1,
                name: "NODE 1",
                engine: frontendConfig.node1.engine,
                model: frontendConfig.node1.model,
                persona_id: frontendConfig.node1.persona_id
            },
            {
                id: 2,
                name: "NODE 2",
                engine: frontendConfig.node2.engine,
                model: frontendConfig.node2.model,
                persona_id: frontendConfig.node2.persona_id
            },
            {
                id: 3,
                name: "NODE 3",
                engine: frontendConfig.node3.engine,
                model: frontendConfig.node3.model,
                persona_id: frontendConfig.node3.persona_id
            }
        ]
    };
}

/**
 * Update NODE display with Engine and Model info (v1.3 Task 3.1.2)
 * IMPORTANT: Only updates ai-unit-name and ai-unit-model, NOT ai-unit-status
 */
function updateNodeDisplay() {
    const config = loadUserConfig();

    const engineLabels = {
        'API_Gemini': 'GEMINI API',
        'API_OpenRouter': 'OPENROUTER',
        'API_Ollama': 'OLLAMA',
        'Claude': 'CLAUDE',
        'Gemini': 'GEMINI',
        'ChatGPT': 'CHATGPT'
    };

    // Update NODE 1 - only update ai-unit-name and ai-unit-model
    const node1LabelElement = elements.claude.querySelector('.ai-unit-name');
    const node1ModelElement = elements.claude.querySelector('.ai-unit-model');
    if (node1LabelElement) {
        node1LabelElement.textContent = engineLabels[config.node1.engine] || config.node1.engine.toUpperCase();
    }
    if (node1ModelElement) {
        node1ModelElement.textContent = config.node1.model || '';
    }

    // Update NODE 2 - only update ai-unit-name and ai-unit-model
    const node2LabelElement = elements.gemini.querySelector('.ai-unit-name');
    const node2ModelElement = elements.gemini.querySelector('.ai-unit-model');
    if (node2LabelElement) {
        node2LabelElement.textContent = engineLabels[config.node2.engine] || config.node2.engine.toUpperCase();
    }
    if (node2ModelElement) {
        node2ModelElement.textContent = config.node2.model || '';
    }

    // Update NODE 3 - only update ai-unit-name and ai-unit-model
    const node3LabelElement = elements.chatgpt.querySelector('.ai-unit-name');
    const node3ModelElement = elements.chatgpt.querySelector('.ai-unit-model');
    if (node3LabelElement) {
        node3LabelElement.textContent = engineLabels[config.node3.engine] || config.node3.engine.toUpperCase();
    }
    if (node3ModelElement) {
        node3ModelElement.textContent = config.node3.model || '';
    }
}

/**
 * Load user config from LocalStorage (v1.3)
 * @returns {Object} - User configuration
 */
function loadUserConfig() {
    try {
        const stored = localStorage.getItem('magin_user_config');
        if (stored) {
            return JSON.parse(stored);
        }
    } catch (error) {
        console.warn('LocalStorage unavailable, using defaults:', error);
    }

    // Return defaults if no stored config
    return {
        node1: { engine: 'Claude', model: null, persona_id: 'neutral_ai' },
        node2: { engine: 'Gemini', model: null, persona_id: 'neutral_ai' },
        node3: { engine: 'ChatGPT', model: null, persona_id: 'neutral_ai' }
    };
}

/**
 * Save user config to LocalStorage (v1.3)
 * @param {Object} config - Configuration to save
 */
function saveUserConfig(config) {
    try {
        localStorage.setItem('magin_user_config', JSON.stringify(config));
    } catch (error) {
        console.warn('LocalStorage unavailable, config not persisted:', error);
    }
}

// Initialize hexagon grid on page load
window.addEventListener('load', async () => {
    generateHexagonGrid();

    // Set initial mode toggle state (FULL MODE = active/right side)
    elements.modeToggle.classList.add('active');

    // Initialize configuration (v1.3)
    await initializeConfig();
    updateNodeDisplay();
});

