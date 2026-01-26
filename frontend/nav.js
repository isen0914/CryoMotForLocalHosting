// Ultra-simple navigation system - loads first, always works
console.log('NAV.JS LOADED');

// Define ALL navigation functions immediately
(function() {
    'use strict';
    
    // Switch tabs
    window.switchTab = function(tabName) {
        console.log('switchTab called:', tabName);
        
        // Hide all sections
        const sections = document.querySelectorAll('.section');
        sections.forEach(s => s.classList.remove('active'));
        
        // Show target section
        const target = document.getElementById(tabName);
        if (target) {
            target.classList.add('active');
            console.log('Section activated:', tabName);
        } else {
            console.error('Section not found:', tabName);
        }
        
        // Update button states
        const buttons = document.querySelectorAll('.nav-btn');
        buttons.forEach(btn => {
            btn.classList.remove('active');
            if (btn.onclick && btn.onclick.toString().includes(tabName)) {
                btn.classList.add('active');
            }
        });
        
        // Handle history tab
        if (tabName === 'history' && typeof loadHistory === 'function') {
            loadHistory();
        }
    };
    
    // Mobile nav
    window.toggleMobileNav = function() {
        console.log('toggleMobileNav called');
        const nav = document.getElementById('mobileNav');
        const overlay = document.getElementById('mobileNavOverlay');
        if (nav) nav.classList.toggle('open');
        if (overlay) overlay.classList.toggle('show');
    };
    
    window.closeMobileNav = function() {
        console.log('closeMobileNav called');
        const nav = document.getElementById('mobileNav');
        const overlay = document.getElementById('mobileNavOverlay');
        if (nav) nav.classList.remove('open');
        if (overlay) overlay.classList.remove('show');
    };
    
    // Toggle step
    window.toggleStep = function(button) {
        const expanded = button.closest('div').nextElementSibling;
        if (expanded && expanded.classList.contains('step-content-expanded')) {
            expanded.classList.toggle('show');
            button.textContent = expanded.classList.contains('show') ? '▲' : '▼';
        }
    };
    
    // Toggle history
    window.toggleHistory = function(button) {
        const expanded = button.closest('div').parentElement.nextElementSibling;
        if (expanded && expanded.classList.contains('history-expanded')) {
            expanded.classList.toggle('show');
            button.textContent = expanded.classList.contains('show') ? '▲' : '▼';
        }
    };
    
    console.log('All navigation functions registered:', {
        switchTab: typeof window.switchTab,
        toggleMobileNav: typeof window.toggleMobileNav,
        closeMobileNav: typeof window.closeMobileNav,
        toggleStep: typeof window.toggleStep,
        toggleHistory: typeof window.toggleHistory
    });
})();
