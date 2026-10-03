/**
 * Shared glass-card toast notifications.
 *
 * Provides _getLiveToastContainer(), _buildLiveToast() and _toastIcon() for
 * use on any page.
 *
 * _buildLiveToast() never parses markup: titles and bodies are strings (text)
 * or DOM nodes the caller built. Callers that need an icon, a link or a button
 * build the element and pass it in.
 */

(function () {
    'use strict';

    // Inject toast icon styles once. The icon is a mask painted with the text
    // color, not an <img> tinted by a filter: it then always matches the title
    // next to it, including the darker shades the light theme swaps in for
    // contrast, which no fixed filter could follow.
    var s = document.createElement('style');
    s.textContent = '.toast-title-icon{display:inline-block;width:16px;height:16px;vertical-align:-3px;margin-right:4px;' +
        'background-color:currentColor;' +
        '-webkit-mask:var(--toast-icon) center/contain no-repeat;mask:var(--toast-icon) center/contain no-repeat}';
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

    // Build the 16px icon used in toast titles. It takes the color of the
    // surrounding text. `variant` is kept as a class for callers that style it.
    window._toastIcon = function (name, variant) {
        const icon = document.createElement('span');
        icon.style.setProperty('--toast-icon', "url('/static/icons/" + encodeURIComponent(name) + ".svg')");
        icon.setAttribute('aria-hidden', 'true');
        icon.className = 'toast-title-icon' + (variant ? ' toast-icon-' + variant : '');
        return icon;
    };

    // Append content to `parent`: strings become text nodes, DOM nodes are
    // appended as-is, arrays are appended entry by entry. Nothing is ever
    // parsed as HTML, so no caller has to escape anything.
    function _appendContent(parent, value) {
        if (value === null || value === undefined) return;
        if (Array.isArray(value)) {
            value.forEach(entry => _appendContent(parent, entry));
        } else if (value instanceof Node) {
            // Appending an existing node parses nothing - the branch below is
            // what turns strings into text. CodeQL does not honour the
            // instanceof guard, so DOM-derived text that always takes the text
            // branch is still reported as reaching here. Any API where callers
            // build nodes and hand them over produces this alert; the only way
            // to remove the flow is to pass markup strings instead.
            // codeql[js/xss-through-dom]
            parent.appendChild(value);
        } else {
            parent.appendChild(document.createTextNode(String(value)));
        }
    }

    // Bodies passed as an array render one line per entry; anything else goes
    // into the body as-is, which is how callers compose a single mixed line.
    function _appendBody(bodyEl, body) {
        if (!Array.isArray(body)) {
            _appendContent(bodyEl, body);
            return;
        }
        body.forEach(entry => {
            const line = document.createElement('div');
            _appendContent(line, entry);
            bodyEl.appendChild(line);
        });
    }

    // Build and display a glass-card toast in the shared upper-right container
    //
    // `onClick`, when given, replaces the default click-to-dismiss on the card
    // body (the corner button still dismisses), so a toast can act as a handle
    // on something else, such as reopening the modal it stands in for.
    //
    // The returned toast has update(title, body, titleColor, autoDismissMs) to
    // rewrite its content in place, so progress replaces the card instead of
    // stacking a new one. Omitted arguments keep their current value; a
    // positive autoDismissMs (re)starts the dismiss timer, 0 cancels it.
    window._buildLiveToast = function (title, body, titleColor, autoDismissMs, onClick) {
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
        closeBtn.textContent = '×';
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
        toast.addEventListener('click', onClick || closeToast);

        const content = document.createElement('div');
        content.style.cssText = 'margin-right: 28px;';

        // Titles are a string, an icon element from _toastIcon()/_mpaIconEl(),
        // or an array mixing the two. Bodies additionally accept an array to
        // get one line per entry. Strings are always rendered as text, so
        // values read back out of the DOM or off the wire stay literal.
        const titleEl = document.createElement('div');
        titleEl.style.cssText = `font-weight:600;font-size:14px;margin-bottom:5px;color:${titleColor};`;
        _appendContent(titleEl, title);

        const bodyEl = document.createElement('div');
        // Addressable so a caller holding the returned toast can update its
        // text in place, rather than stacking a new toast per progress step.
        bodyEl.className = 'toast-body';
        bodyEl.style.cssText = 'opacity:0.85;font-size:13px;';
        _appendBody(bodyEl, body);

        content.append(titleEl, bodyEl);

        toast.appendChild(closeBtn);
        toast.appendChild(content);
        _getLiveToastContainer().appendChild(toast);

        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        });

        // A duration of 0 keeps the toast up until it is dismissed or its owner
        // replaces it, for progress that outlives any fixed timeout.
        let timer = autoDismissMs > 0 ? setTimeout(closeToast, autoDismissMs) : null;
        toast.closeToast = () => { if (timer) clearTimeout(timer); closeToast(); };

        toast.update = (newTitle, newBody, newTitleColor, newDismissMs) => {
            if (newTitle !== undefined && newTitle !== null) {
                titleEl.textContent = '';
                _appendContent(titleEl, newTitle);
            }
            if (newTitleColor) titleEl.style.color = _adaptTitleColor(newTitleColor, isDark);
            if (newBody !== undefined && newBody !== null) {
                bodyEl.textContent = '';
                _appendBody(bodyEl, newBody);
            }
            if (newDismissMs !== undefined) {
                if (timer) clearTimeout(timer);
                timer = newDismissMs > 0 ? setTimeout(closeToast, newDismissMs) : null;
            }
        };

        return toast;
    };

    // Type-to-color map for showNotification
    var _notifyColors = {
        success: '#28a745',
        error:   '#dc3545',
        warning: '#F7931A',
        info:    '#17a2b8'
    };

    // Type-to-icon map for showNotification. No 'info' entry - no icon asset
    // fits that case well yet, so info toasts stay title-only.
    var _notifyIcons = {
        success: { name: 'check', variant: 'success' },
        error:   { name: 'error', variant: 'error' },
        warning: { name: 'error', variant: 'accent' }
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
        var icon = _notifyIcons[type];
        var titleParts = icon
            ? [_toastIcon(icon.name, icon.variant), ' ' + title]
            : title;
        // Pass as an array so the body renders as text. Messages here
        // routinely carry filenames and other values read back out of the DOM.
        _buildLiveToast(titleParts, [message], color, duration);
    };
})();
