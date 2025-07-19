// Basketball data
const basketballData = {
    "teams": {
        "3204": "БК Новосибирск",
        "741": "ЦСКА-2"
    },
    "arenas": {
        "11926": "ДС Динамо (Москва)",
        "11745": "СКК Север (Новосибирск)"
    }
};

// DOM elements
const teamSelect = document.getElementById('team-select');
const arenaSelect = document.getElementById('arena-select');
const generateBtn = document.getElementById('generate-btn');
const copyBtn = document.getElementById('copy-btn');
const generatedLinkInput = document.getElementById('generated-link');
const resultContainer = document.getElementById('result-container');
const copyFeedback = document.getElementById('copy-feedback');
const appleCalendarBtn = document.getElementById('apple-calendar-btn');
const googleCalendarBtn = document.getElementById('google-calendar-btn');
const outlookCalendarBtn = document.getElementById('outlook-calendar-btn');

// Initialize the application
function init() {
    populateSelects();
    setupEventListeners();
}

// Populate select dropdowns with data
function populateSelects() {
    // Populate teams
    Object.entries(basketballData.teams).forEach(([id, name]) => {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = name;
        teamSelect.appendChild(option);
    });

    // Populate arenas
    Object.entries(basketballData.arenas).forEach(([id, name]) => {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = name;
        arenaSelect.appendChild(option);
    });
}

// Setup all event listeners
function setupEventListeners() {
    // Enable/disable generate button based on selections
    function updateGenerateButton() {
        const teamSelected = teamSelect.value !== '';
        const arenaSelected = arenaSelect.value !== '';
        generateBtn.disabled = !(teamSelected && arenaSelected);
        
        if (teamSelected && arenaSelected) {
            generateBtn.classList.add('active');
        } else {
            generateBtn.classList.remove('active');
        }
    }

    teamSelect.addEventListener('change', updateGenerateButton);
    arenaSelect.addEventListener('change', updateGenerateButton);

    // Generate base link parameters once and reuse
    function generateLink() {
        const teamId = teamSelect.value;
        const arenaId = arenaSelect.value;
        
        if (teamId && arenaId) {
            return `d5dud9hvel1i5o2a72rj.l3hh3szr.apigw.yandexcloud.net/rbf2ics?team_id=${teamId}&arena_id=${arenaId}`;
        }
        return '';
    }

    // Generate link
    generateBtn.addEventListener('click', function() {
        const link = generateLink();
        
        if (link) {
            const generatedLink = `https://${link}`;
            generatedLinkInput.value = generatedLink;
            resultContainer.classList.remove('hidden');
            
            // Smooth scroll to result
            resultContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    });

    // Copy to clipboard
    copyBtn.addEventListener('click', function() {
        generatedLinkInput.select();
        generatedLinkInput.setSelectionRange(0, 99999); // For mobile devices

        try {
            document.execCommand('copy');
            showCopyFeedback();
        } catch (error) {
            console.error('Failed to copy to clipboard:', error);
        }
    });

    // Select all text when clicking on the input
    generatedLinkInput.addEventListener('click', function() {
        this.select();
    });

    // Apple Calendar button
    appleCalendarBtn.addEventListener('click', function() {
        const link = generateLink();
        
        if (link) {
            const webcalLink = `webcal://${link}`;
            window.open(webcalLink, '_blank');
        }
    });

    // Google Calendar button
    googleCalendarBtn.addEventListener('click', function() {
        const link = generateLink();
        
        if (link) {
            const googleCalendarLink = `https://calendar.google.com/calendar/render?cid=webcal://${link}`.replace('&','%26');
            window.open(googleCalendarLink, '_blank');
        }
    });

    // Outlook Calendar button
    outlookCalendarBtn.addEventListener('click', function() {
        const link = generateLink();
        
        if (link) {
            const outlookCalendarLink = `https://outlook.live.com/owa?path=/calendar/action/compose&rru=addsubscription&url=webcal://${link}`.replace('&','%26');
            window.open(outlookCalendarLink, '_blank');
        }
    });
}

// Show copy feedback
function showCopyFeedback() {
    copyFeedback.classList.remove('hidden');
    copyBtn.textContent = 'Copied!';
    copyBtn.classList.add('copied');
    
    setTimeout(function() {
        copyFeedback.classList.add('hidden');
        copyBtn.textContent = 'Copy';
        copyBtn.classList.remove('copied');
    }, 2000);
}

// Start the application when DOM is loaded
document.addEventListener('DOMContentLoaded', init);