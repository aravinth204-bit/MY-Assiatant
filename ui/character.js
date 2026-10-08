let currentPose = 'idle';
let animationTimer = null;
let bubbleHideTimer = null;
let orientationMode = 'normal';
let orientationDirection = 'right';

let isPointerDown = false;
let isDraggingMascot = false;
let startScreenX = 0;
let startScreenY = 0;
let isMovingWindow = false;

// **NEW: Mascot style system**
let currentMascotStyle = 'default'; // loaded from config
let mascotStyles = {};

// **NEW: Voice system**
let voiceEnabled = false;
let voiceLanguage = 'en-IN';

// **NEW: Personality system**
let personality = 'friendly';
let personalitySettings = {
    friendly: {
        greeting: 'Hi there! How can I help you today?',
        formal_prefix: '',
        casual_suffix: '!',
        emoji: '👋'
    },
    professional: {
        greeting: 'Good day. How may I assist you?',
        formal_prefix: '',
        casual_suffix: '.',
        emoji: '🤖'
    },
    funny: {
        greeting: 'Hello! I promise I\'m more useful than I look!',
        formal_prefix: '',
        casual_suffix: '! 😄',
        emoji: '😄'
    }
};

// Initialize mascot styles from config
function initMascotStyles(styles) {
    mascotStyles = styles;
    if (styles[currentMascotStyle]) {
        applyMascotStyle(styles[currentMascotStyle]);
    }
}

function applyMascotStyle(style) {
    currentMascotStyle = style.name || 'default';
    const colors = style.colors || { primary: '#14b8a6', secondary: '#f43f5e' };
    
    // Update CSS variables for the mascot
    const root = document.documentElement;
    root.style.setProperty('--mascot-primary', colors.primary);
    root.style.setProperty('--mascot-secondary', colors.secondary);
    
    // Update speech bubble colors
    const bubble = document.querySelector('.speech-bubble');
    if (bubble) {
        bubble.style.borderColor = 'rgba(255, 255, 255, 0.28)';
        bubble.style.background = `rgba(15, 23, 42, 0.96)`;
    }
    
    console.log(`Mascot style applied: ${style.name || 'default'}`);
}

// **NEW: Initialize voice**
function initVoice(enabled, language) {
    voiceEnabled = enabled;
    voiceLanguage = language;
}

// **NEW: Speak text using Web Speech API**
function speakText(text) {
    if (!voiceEnabled) return;
    
    // Check if SpeechSynthesis is supported
    if (!('speechSynthesis' in window)) {
        console.log('Text-to-Speech not supported in this browser');
        return;
    }
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = voiceLanguage || 'en-US';
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;
    
    window.speechSynthesis.speak(utterance);
}

// **NEW: Apply personality to speech bubble**
function applyPersonality() {
    const settings = personalitySettings[personality] || personalitySettings.friendly;
    
    // Update global CSS vars based on personality
    const root = document.documentElement;
    root.style.setProperty('--personality-emoji', settings.emoji);
    
    // Could also adjust speech bubble styling, message formatting, etc.
    console.log(`Personality applied: ${personality}`);
}

function setPose(pose, message = null) {
    currentPose = pose;
    const imgElement = document.getElementById('sprite-img');
    const webLine = document.getElementById('web-line');
    
    if (animationTimer) {
        clearInterval(animationTimer);
        animationTimer = null;
    }

    imgElement.className = 'mascot-img';

    const playFrames = (frameNumbers, intervalMs = 120, loop = true, onComplete = null) => {
        let frameIndex = 0;
        imgElement.src = FRAME_ASSETS[frameNumbers[frameIndex] - 1];
        animationTimer = setInterval(() => {
            if (!loop && frameIndex === frameNumbers.length - 1) {
                clearInterval(animationTimer);
                animationTimer = null;
                if (onComplete) onComplete();
                return;
            }
            frameIndex = (frameIndex + 1) % frameNumbers.length;
            imgElement.src = FRAME_ASSETS[frameNumbers[frameIndex] - 1];
        }, intervalMs);
    };

    if (pose === 'startup') {
        imgElement.style.transform = '';
        playFrames([1, 2, 3, 4], 140, false, () => {
            // Apply personality greeting format
            const settings = personalitySettings[personality] || personalitySettings.friendly;
            const formattedMessage = `${settings.formal_prefix}${settings.greeting}${settings.casual_suffix}`;
            showSpeechBubble(formattedMessage);
            if (voiceEnabled) {
                speakText(formattedMessage);
            }
        });
    }
    else if (pose === 'walk_right') {
        imgElement.style.transform = '';
        playFrames(Array.from({ length: 9 }, (_, index) => index + 5));
    }
    else if (pose === 'climb_up') {
        imgElement.style.transform = '';
        playFrames(Array.from({ length: 8 }, (_, index) => index + 15));
    }
    else if (pose === 'ceiling_walk') {
        imgElement.style.transform = '';
        playFrames(Array.from({ length: 7 }, (_, index) => index + 25));
    }
    else if (pose === 'climb_down') {
        imgElement.style.transform = '';
        playFrames([33, 34, 35]);
    }
    else if (pose === 'landing') {
        imgElement.style.transform = '';
        playFrames([36, 37, 38, 39, 40], 160, false);
    }
    else if (pose === 'idle') {
        imgElement.src = FRAME_ASSETS[39];
    } 
    else if (pose === 'walk') {
        const frameNumbers = Array.from({ length: 9 }, (_, index) => 8 + index);
        playFrames(frameNumbers);
    } 
    else if (pose === 'webshoot') {
        const frameNumbers = Array.from({ length: 8 }, (_, index) => 17 + index);
        playFrames(frameNumbers);
    } 
    else if (pose === 'celebrate') {
        playFrames([1, 2, 3, 4, 5, 6, 7, 8], 140);
        setTimeout(() => {
            setPose('idle');
        }, 2500);
    } 
    else {
        imgElement.src = FRAME_ASSETS[39];
    }

    if (message) {
        // Apply personality formatting to message
        const settings = personalitySettings[personality] || personalitySettings.friendly;
        const formattedMessage = `${settings.formal_prefix}${message}${settings.casual_suffix}`;
        showSpeechBubble(formattedMessage);
        if (voiceEnabled) {
            speakText(formattedMessage);
        }
    }
}

function showSpeechBubble(text, durationMs = 5000) {
    const app = document.getElementById('app-container');
    const bubble = document.getElementById('speech-bubble');
    const textEl = document.getElementById('speech-text');
    
    if (!text || (app && app.classList.contains('time-warning-mode'))) return;
    textEl.innerText = text;
    bubble.classList.remove('hidden');

    if (bubbleHideTimer) {
        clearTimeout(bubbleHideTimer);
    }

    bubbleHideTimer = setTimeout(() => {
        if (!app || !app.classList.contains('time-warning-mode')) {
            bubble.classList.add('hidden');
        }
        bubbleHideTimer = null;
    }, durationMs);
}

function openControlCenter(event) {
    if (event) event.stopPropagation();
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.open_settings();
    }
}

const notificationCooldowns = {};
function canNotify(key, cooldownMs = 300000) {
    const now = Date.now();
    const last = notificationCooldowns[key] || 0;
    if (now - last >= cooldownMs) {
        notificationCooldowns[key] = now;
        return true;
    }
    return false;
}

function checkSystemStatus() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.get_system_stats().then(stats => {
            if (stats.is_tired && currentPose !== 'tired') {
                if (canNotify('tired_warning', 300000)) {
                    setPose('tired', 'Phew! System high load or low battery...');
                }
            } else if (stats.is_storage_alert && currentPose !== 'alert') {
                if (canNotify('storage_warning', 300000)) {
                    setPose('alert', 'Warning: Free storage space is under 10%!');
                }
            }
        }).catch(err => console.log('Error checking stats:', err));
    }
}

window.setPose = setPose;
window.setOrientation = setOrientation;
window.triggerWebLine = triggerWebLine;
window.clearWebLine = clearWebLine;
window.showTimeLimitWarning = showTimeLimitWarning;
window.hideTimeLimitWarning = hideTimeLimitWarning;
window.showSpeechBubble = showSpeechBubble;
window.openControlCenter = openControlCenter;

// **NEW: Export functions for settings UI**
window.initMascotStyles = initMascotStyles;
window.applyMascotStyle = applyMascotStyle;
window.initVoice = initVoice;
window.speakText = speakText;
window.applyPersonality = applyPersonality;
window.currentMascotStyle = currentMascotStyle;
window.personality = personality;