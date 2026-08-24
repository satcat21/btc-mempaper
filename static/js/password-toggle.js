/**
 * Show/hide toggle for password fields.
 *
 * A hidden field is only useful while nobody is checking it. Entering a Wi-Fi
 * key or a new admin password from a phone, with no way to read back what was
 * typed, turns a typo into a failed connection or a lockout that is discovered
 * later and traced with difficulty. Every password input on the page gets a
 * control to reveal its own contents.
 *
 * Applied by observation rather than by calling a function at each input, for
 * two reasons: the settings page builds most of its fields in JavaScript, some
 * of them inside modals that do not exist until they are opened, and a list of
 * call sites is a list to keep in step with every new field. Watching for the
 * inputs themselves cannot fall behind.
 *
 * Styles travel with the component so a page needs only the one script tag.
 * The mask-image treatment matches .themed-mask-icon in config.css: the SVG
 * colours itself from currentColor, so it stays legible on either theme and on
 * the hotspot page, which defines no theme variables at all.
 */
(function () {
    'use strict';

    var SHOWN = '/static/icons/visibility.svg';
    var HIDDEN = '/static/icons/visibility_off.svg';
    var STYLE_ID = 'mempaper-password-toggle-style';

    function injectStyles() {
        if (document.getElementById(STYLE_ID)) return;
        var css = [
            '.pw-toggle-wrap{position:relative;display:block;width:100%}',
            '.pw-toggle-wrap>input{width:100%;box-sizing:border-box;padding-right:2.4em}',
            '.pw-toggle-btn{position:absolute;top:50%;right:.55em;transform:translateY(-50%);',
            'display:flex;align-items:center;justify-content:center;width:1.9em;height:1.9em;',
            'padding:0;border:0;background:transparent;cursor:pointer;opacity:.65;',
            'border-radius:4px;transition:opacity .12s ease}',
            '.pw-toggle-btn:hover,.pw-toggle-btn:focus-visible{opacity:1}',
            '.pw-toggle-btn:focus-visible{outline:2px solid currentColor;outline-offset:1px}',
            '.pw-toggle-btn>span{display:block;width:1.15em;height:1.15em;',
            'background-color:currentColor;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;',
            '-webkit-mask-size:contain;mask-size:contain;',
            '-webkit-mask-position:center;mask-position:center}',
            '@media (prefers-reduced-motion:reduce){.pw-toggle-btn{transition:none}}'
        ].join('');
        var el = document.createElement('style');
        el.id = STYLE_ID;
        el.textContent = css;
        (document.head || document.documentElement).appendChild(el);
    }

    function label(revealed) {
        var t = window.translations || {};
        return revealed
            ? (t.hide_password || 'Hide password')
            : (t.show_password || 'Show password');
    }

    function paint(icon, btn, revealed) {
        var path = revealed ? HIDDEN : SHOWN;
        icon.style.webkitMaskImage = "url('" + path + "')";
        icon.style.maskImage = "url('" + path + "')";
        btn.title = label(revealed);
        btn.setAttribute('aria-label', btn.title);
        btn.setAttribute('aria-pressed', revealed ? 'true' : 'false');
    }

    function decorate(input) {
        if (!input || input.dataset.pwToggle === '1') return;
        if (input.type !== 'password') return;
        // A field nobody can reach needs no control, and wrapping one that is
        // display:none would measure zero and place the button at random.
        if (input.getAttribute('aria-hidden') === 'true') return;
        input.dataset.pwToggle = '1';

        var parent = input.parentNode;
        if (!parent) return;

        var wrap = document.createElement('div');
        wrap.className = 'pw-toggle-wrap';
        parent.insertBefore(wrap, input);
        wrap.appendChild(input);

        var btn = document.createElement('button');
        // Explicitly a button: these inputs sit inside <form> elements, where
        // the default type is submit and a click would post the form instead
        // of revealing anything.
        btn.type = 'button';
        btn.className = 'pw-toggle-btn';
        btn.tabIndex = 0;

        var icon = document.createElement('span');
        btn.appendChild(icon);
        paint(icon, btn, false);

        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var revealed = input.type === 'text';
            input.type = revealed ? 'password' : 'text';
            paint(icon, btn, !revealed);
            // The caret goes back where it was: switching type moves it to the
            // end, which is wrong for someone correcting a character mid-string.
            try {
                var pos = input.value.length;
                input.focus({ preventScroll: true });
                input.setSelectionRange(pos, pos);
            } catch (_) { /* setSelectionRange is not valid on every type */ }
        });

        wrap.appendChild(btn);
    }

    function scan(root) {
        if (!root || !root.querySelectorAll) return;
        var found = root.querySelectorAll('input[type="password"]');
        for (var i = 0; i < found.length; i++) decorate(found[i]);
    }

    function start() {
        injectStyles();
        scan(document);
        if (!window.MutationObserver) return;
        new MutationObserver(function (records) {
            for (var i = 0; i < records.length; i++) {
                var rec = records[i];
                // A field that becomes a password field after it is already on
                // the page is not an insertion, so watching children alone
                // would let it through undecorated. decorate() is idempotent,
                // and the toggle's own type flipping lands here harmlessly.
                if (rec.type === 'attributes') {
                    decorate(rec.target);
                    continue;
                }
                var added = rec.addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var node = added[j];
                    if (node.nodeType !== 1) continue;
                    if (node.tagName === 'INPUT') decorate(node);
                    else scan(node);
                }
            }
        }).observe(document.documentElement, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['type']
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
