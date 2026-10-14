// Gallery navigation for the image preview modals (memes, OPSec, Nostr).
// Part 10, loaded after the modals. Left/right arrows, the < > buttons over
// the image, or a swipe step to the neighbouring thumbnail without closing
// the preview.
//
// It steps through the thumbnails as the page shows them - search filter
// and all - and opens each by clicking it, so every kind keeps its own
// opening logic: tags and rename for memes, state for Nostr posts.

// Only the thumbnail picture itself, which carries data-filename: a bare
// 'img' also matched the icons inside each thumbnail's Download and Delete
// buttons, and a step that landed on one clicked it.
const GALLERIES = {
    'meme-modal':  { items: '#memes-list .meme-thumbnail img[data-filename]' },
    'opsec-modal': { items: '#opsec-images-list .meme-thumbnail img[data-filename]' },
    'nostr-modal': { items: '#nostr-pool-list .nostr-post-tile' },
};

// The thumbnail each modal was last opened from, and its position as a
// fallback when that thumbnail has since been removed (deleted, re-rendered).
const _galleryCurrent = {};

function _galleryItems(modalId) {
    return Array.from(document.querySelectorAll(GALLERIES[modalId].items));
}

function _galleryOpenModal() {
    return Object.keys(GALLERIES)
        .map(id => document.getElementById(id))
        .find(m => m && m.style.display === 'flex') || null;
}

// Where the open image sits in the grid: {index, items}. When its thumbnail
// is gone (deleted), the neighbours have closed up around its old position.
function _galleryPosition(modalId) {
    const items = _galleryItems(modalId);
    const cur = _galleryCurrent[modalId] || {};
    let index = items.indexOf(cur.el);
    let removed = false;
    if (index < 0) {
        index = Math.min(cur.index ?? 0, items.length);
        removed = true;
    }
    return { items, index, removed };
}

// The neighbour in the grid, or null at either end - no wrapping round, so
// the arrows move exactly as the eye would across the grid.
function _galleryTarget(modalId, delta) {
    const { items, index, removed } = _galleryPosition(modalId);
    // A removed thumbnail's right neighbour now stands at its old index.
    const target = removed && delta > 0 ? index : index + delta;
    return target >= 0 && target < items.length ? items[target] : null;
}

function galleryStep(modalId, delta) {
    const next = _galleryTarget(modalId, delta);
    if (!next) return;
    // Lazy-loaded thumbnails far down the grid get scrolled to, so the grid
    // keeps loading and the position stays visible behind the modal.
    next.scrollIntoView({ block: 'nearest' });
    next.click();
    const modal = document.getElementById(modalId);
    if (modal) _galleryUpdateButtons(modal);
}

function _galleryUpdateButtons(modal) {
    modal.querySelector('.gallery-nav.prev').style.display = _galleryTarget(modal.id, -1) ? '' : 'none';
    modal.querySelector('.gallery-nav.next').style.display = _galleryTarget(modal.id, 1) ? '' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    const chevron = (d) => `<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><path d="${d}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

    Object.keys(GALLERIES).forEach(modalId => {
        const modal = document.getElementById(modalId);
        const stage = modal?.querySelector('.meme-preview-container');
        if (!stage) return;

        [['prev', -1, 'M15 5l-7 7 7 7', window.translations?.gallery_previous || 'Previous'],
         ['next', 1, 'M9 5l7 7-7 7', window.translations?.gallery_next || 'Next']]
            .forEach(([cls, delta, path, label]) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = `gallery-nav ${cls}`;
                btn.title = label;
                btn.setAttribute('aria-label', label);
                btn.innerHTML = chevron(path);
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    galleryStep(modalId, delta);
                });
                stage.appendChild(btn);
            });

        // Swipe on touch screens.
        let startX = null;
        stage.addEventListener('touchstart', (e) => { startX = e.touches[0].clientX; }, { passive: true });
        stage.addEventListener('touchend', (e) => {
            if (startX === null) return;
            const dx = e.changedTouches[0].clientX - startX;
            startX = null;
            if (Math.abs(dx) > 50) galleryStep(modalId, dx < 0 ? 1 : -1);
        });

        // Buttons only where there is somewhere to go: on opening, and when
        // the grid behind loads more thumbnails (the meme grid adds 50 at a
        // time as it is scrolled), so the last loaded one gets its > back.
        new MutationObserver(() => {
            if (modal.style.display === 'flex') _galleryUpdateButtons(modal);
        }).observe(modal, { attributes: true, attributeFilter: ['style'] });
        const listSelector = GALLERIES[modalId].items.split(' ')[0];
        new MutationObserver(() => {
            if (modal.style.display === 'flex' && document.querySelector(listSelector)) {
                _galleryUpdateButtons(modal);
            }
        }).observe(document.body, { childList: true, subtree: true });
    });

    // Remember which thumbnail opened a modal - by a real click or by a step.
    document.addEventListener('click', (e) => {
        for (const [modalId, cfg] of Object.entries(GALLERIES)) {
            const el = e.target.closest?.(cfg.items);
            if (el) {
                _galleryCurrent[modalId] = { el, index: _galleryItems(modalId).indexOf(el) };
                return;
            }
        }
    }, true);

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        const modal = _galleryOpenModal();
        if (!modal) return;
        // Not while typing (rename, tags), nor under a confirm dialog: a step
        // there would change which image the pending Delete applies to.
        const t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
        if (document.querySelector('.confirm-modal-overlay')) return;
        e.preventDefault();
        galleryStep(modal.id, e.key === 'ArrowRight' ? 1 : -1);
    });
});
