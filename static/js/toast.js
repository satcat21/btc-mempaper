/**
 * Shared glass-card toast notifications.
 *
 * Provides _getLiveToastContainer() and _buildLiveToast() for use on any page.
 */

(function () {
    'use strict';

    // Inject toast icon styles once
    var s = document.createElement('style');
    s.textContent = '.toast-title-icon{vertical-align:middle;margin-right:4px;opacity:0.85}' +
        '.dark-mode .toast-title-icon{filter:invert(1)}' +
        '.toast-icon-accent{filter:brightness(0) saturate(100%) invert(62%) sepia(65%) saturate(2028%) hue-rotate(6deg) brightness(100%) contrast(93%)!important}' +
        '.toast-icon-success{filter:brightness(0) saturate(100%) invert(44%) sepia(72%) saturate(456%) hue-rotate(97deg) brightness(96%) contrast(97%)!important}';
    document.head.appendChild(s);

    // Return (or create) the shared upper-right toast stack container
    window._getLiveToastContainer = function () {
        let el = document.getElementById('block-toast-container');
        if (!el) {
            el = document.createElement('div');
            el.id = 'block-toast-container';
            el.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 100100;
                font-family: 'Roboto', Arial, sans-serif;
                isolation: isolate;
            `;
            document.body.appendChild(el);
        }
        // Ensure container is the last body child so it paints above nav elements
        // whose backdrop-filter creates competing stacking contexts
        if (el.nextSibling) document.body.appendChild(el);

        // On mobile, keep the toast stack clear of the config page's sticky
        // section-nav so it doesn't cover the pill track and block horizontal
        // drags on it. Desktop keeps the original fixed top:20px position.
        const nav = document.querySelector('.section-nav');
        el.style.top = (nav && window.matchMedia('(max-width: 999px)').matches)
            ? (nav.getBoundingClientRect().bottom + 8) + 'px'
            : '20px';

        return el;
    };

    // Dark-mode-tuned accent colors read poorly as text on the light theme's
    // near-white card (contrast as low as ~2.3:1 for the brand orange). Swap
    // in AA-safe equivalents when the light theme is active; anything not in
    // this map (e.g. per-user donation/section colors, already split by
    // theme via _getLiveToastColor) passes through unchanged.
    var _lightModeColorMap = {
        '#f7931a': '#b7791f', // brand orange
        '#22c55e': '#15803d', // green-500
        '#28a745': '#15803d', // bootstrap green
        '#17a2b8': '#0e7490', // info cyan
        '#ef4444': '#dc2626'  // red-500
    };
    function _adaptTitleColor(color, isDark) {
        if (isDark || !color) return color;
        return _lightModeColorMap[color.toLowerCase()] || color;
    }

    // Build and display a glass-card toast in the shared upper-right container
    window._buildLiveToast = function (titleText, bodyHtml, titleColor, autoDismissMs) {
        if (autoDismissMs === undefined) autoDismissMs = 6000;
        const isDark      = document.body.classList.contains('dark-mode');
        titleColor = _adaptTitleColor(titleColor, isDark);
        const toastBg     = isDark ? 'rgba(30, 30, 36, 0.92)'  : 'rgba(255, 255, 255, 0.95)';
        const toastColor  = isDark ? '#e8e8ec'                  : '#1a1a2e';
        const toastBorder = isDark ? 'rgba(255, 255, 255, 0.08)': 'rgba(0, 0, 0, 0.1)';
        const toastShadow = isDark
            ? '0 8px 32px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255,255,255,0.06)'
            : '0 8px 32px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0,0,0,0.04)';
        const closeBtnBg      = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
        const closeBtnColor   = isDark ? '#9a9aaa'                   : '#555';
        const closeBtnHoverBg = isDark ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.12)';

        const toast = document.createElement('div');
        toast.style.cssText = `
            background: ${toastBg};
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            color: ${toastColor};
            padding: 14px 18px;
            border-radius: 14px;
            box-shadow: ${toastShadow};
            border: 1px solid ${toastBorder};
            margin-bottom: 10px;
            min-width: 280px;
            max-width: 360px;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            font-size: 13px;
            line-height: 1.4;
            cursor: pointer;
        `;

        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '&times;';
        closeBtn.setAttribute('aria-label', 'Close notification');
        closeBtn.style.cssText = `
            position: absolute;
            top: 8px;
            right: 8px;
            background: ${closeBtnBg};
            border: none;
            color: ${closeBtnColor};
            font-size: 18px;
            cursor: pointer;
            width: 26px;
            height: 26px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            transition: background-color 0.2s;
            font-weight: bold;
            line-height: 1;
        `;

        const closeToast = () => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 400);
        };

        closeBtn.addEventListener('click', e => { e.stopPropagation(); closeToast(); });
        closeBtn.addEventListener('mouseenter', () => { closeBtn.style.backgroundColor = closeBtnHoverBg; });
        closeBtn.addEventListener('mouseleave', () => { closeBtn.style.backgroundColor = closeBtnBg; });
        toast.addEventListener('click', closeToast);

        const content = document.createElement('div');
        content.style.cssText = 'margin-right: 28px;';
        content.innerHTML =
            `<div style="font-weight:600;font-size:14px;margin-bottom:5px;color:${titleColor};">${titleText}</div>` +
            `<div style="opacity:0.85;font-size:13px;">${bodyHtml}</div>`;

        toast.appendChild(closeBtn);
        toast.appendChild(content);
        _getLiveToastContainer().appendChild(toast);

        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        });

        const timer = setTimeout(closeToast, autoDismissMs);
        toast.closeToast = () => { clearTimeout(timer); closeToast(); };
    };

    // Type-to-colour map for showNotification
    var _notifyColors = {
        success: '#28a745',
        error:   '#dc3545',
        warning: '#F7931A',
        info:    '#17a2b8'
    };

    // Drop-in replacement for the old showNotification(message, type, duration)
    window.showNotification = function (message, type, duration) {
        if (!type) type = 'info';
        if (!duration) duration = 5000;
        var t = window.translations || {};
        var color = _notifyColors[type] || _notifyColors.info;
        var titles = {
            success: t.toast_success || 'Success',
            error:   t.toast_error   || 'Error',
            warning: t.toast_warning || 'Warning',
            info:    t.toast_info    || 'Info'
        };
        var title = titles[type] || '';
        // Escape HTML in message
        var safe = message.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        _buildLiveToast(title, safe, color, duration);
    };
})();
