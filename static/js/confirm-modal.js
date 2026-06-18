/**
 * Themed confirmation & alert modal – replaces native confirm() and alert().
 *
 * Usage:
 *   const ok = await showConfirmModal({ title, message, confirmText, cancelText, danger });
 *   await showAlertModal({ title, message, buttonText });
 */

(function () {
    'use strict';

    // ── Helpers ────────────────────────────────────────────────
    function t(key, fallback) {
        return (window.translations && window.translations[key]) || fallback;
    }

    function createOverlay() {
        const overlay = document.createElement('div');
        overlay.className = 'confirm-modal-overlay';
        return overlay;
    }

    function createDialog() {
        const dialog = document.createElement('div');
        dialog.className = 'confirm-modal-dialog';
        return dialog;
    }

    // ── Confirm Modal ──────────────────────────────────────────
    window.showConfirmModal = function ({ title, message, confirmText, cancelText, danger, icon } = {}) {
        return new Promise(resolve => {
            const overlay = createOverlay();
            const dialog = createDialog();

            const heading = document.createElement('h3');
            heading.className = 'confirm-modal-title';
            if (icon) {
                heading.innerHTML = `<img src="${icon}" alt="" class="modal-title-icon"> ${title || t('confirm', 'Confirm')}`;
            } else {
                heading.textContent = title || t('confirm', 'Confirm');
            }

            const body = document.createElement('p');
            body.className = 'confirm-modal-message';
            body.textContent = message || '';

            const buttons = document.createElement('div');
            buttons.className = 'confirm-modal-buttons';

            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'confirm-modal-btn cancel';
            cancelBtn.textContent = cancelText || t('cancel', 'Cancel');

            const confirmBtn = document.createElement('button');
            confirmBtn.className = 'confirm-modal-btn ' + (danger ? 'danger' : 'confirm');
            confirmBtn.textContent = confirmText || t('confirm', 'Confirm');

            buttons.appendChild(cancelBtn);
            buttons.appendChild(confirmBtn);

            dialog.appendChild(heading);
            dialog.appendChild(body);
            dialog.appendChild(buttons);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            // Animate in
            requestAnimationFrame(() => overlay.classList.add('visible'));

            function close(result) {
                overlay.classList.remove('visible');
                overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
                // Fallback removal in case transitionend doesn't fire
                setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 350);
                resolve(result);
            }

            confirmBtn.addEventListener('click', () => close(true));
            cancelBtn.addEventListener('click', () => close(false));
            overlay.addEventListener('click', e => { if (e.target === overlay) close(false); });

            // Keyboard: Escape = cancel, Enter = confirm
            function onKey(e) {
                if (e.key === 'Escape') { close(false); document.removeEventListener('keydown', onKey); }
                if (e.key === 'Enter') { close(true); document.removeEventListener('keydown', onKey); }
            }
            document.addEventListener('keydown', onKey);

            confirmBtn.focus();
        });
    };

    // ── Alert Modal ────────────────────────────────────────────
    window.showAlertModal = function ({ title, message, buttonText, icon } = {}) {
        return new Promise(resolve => {
            const overlay = createOverlay();
            const dialog = createDialog();

            const heading = document.createElement('h3');
            heading.className = 'confirm-modal-title';
            if (icon) {
                heading.innerHTML = `<img src="${icon}" alt="" class="modal-title-icon"> ${title || ''}`;
            } else {
                heading.textContent = title || '';
            }

            const body = document.createElement('p');
            body.className = 'confirm-modal-message';
            body.textContent = message || '';

            const buttons = document.createElement('div');
            buttons.className = 'confirm-modal-buttons';

            const okBtn = document.createElement('button');
            okBtn.className = 'confirm-modal-btn confirm';
            okBtn.textContent = buttonText || 'OK';

            buttons.appendChild(okBtn);

            dialog.appendChild(heading);
            dialog.appendChild(body);
            dialog.appendChild(buttons);
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            requestAnimationFrame(() => overlay.classList.add('visible'));

            function close() {
                overlay.classList.remove('visible');
                overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
                setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 350);
                resolve();
            }

            okBtn.addEventListener('click', close);
            overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

            function onKey(e) {
                if (e.key === 'Escape' || e.key === 'Enter') { close(); document.removeEventListener('keydown', onKey); }
            }
            document.addEventListener('keydown', onKey);

            okBtn.focus();
        });
    };
})();
