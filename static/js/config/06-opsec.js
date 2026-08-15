// OPSec image management.
// Part 6 of 8, split from config.js. Load order matters:
// these run as classic scripts sharing one global scope.

// --- OPSec Image Management ---

function createOpsecThumb(img) {
    const thumb = document.createElement('div');
    thumb.className = 'meme-thumbnail';
    thumb.style.position = 'relative';

    const imgEl = document.createElement('img');
    imgEl.src = img.thumb_url || img.url;
    imgEl.alt = img.filename;
    imgEl.dataset.filename = img.filename;
    imgEl.loading = 'lazy';
    imgEl.style.cssText = 'width:100%; aspect-ratio:1; object-fit:cover; border-radius:8px; cursor:pointer;';
    imgEl.title = img.filename;
    imgEl.onclick = () => openOpsecModal(img.filename, img.url);

    const nameEl = document.createElement('div');
    nameEl.className = 'meme-filename';
    nameEl.style.cssText = 'font-size:0.7rem; text-align:center; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding: 2px 4px;';
    nameEl.textContent = img.filename;

    const actionsEl = document.createElement('div');
    actionsEl.className = 'meme-actions';
    actionsEl.style.cssText = 'display:flex; justify-content:center; gap:4px; margin-top:4px;';
    actionsEl.append(
        buildActionButton('download', window.translations?.download_meme || 'Download', '',
            () => downloadOpsecImage(img.filename)),
        buildActionButton('delete', window.translations?.delete_meme || 'Delete', 'delete',
            () => showOpsecDeleteModal(img.filename))
    );

    thumb.appendChild(imgEl);
    thumb.appendChild(nameEl);
    thumb.appendChild(actionsEl);
    return thumb;
}

// Opsec infinite scroll
let opsecScrollObserver = null;
let opsecScrollLoading = false;

function setupOpsecInfiniteScroll(sentinel) {
    if (opsecScrollObserver) {
        opsecScrollObserver.disconnect();
    }
    const scrollContainer = document.querySelector('.opsec-scroll-container');
    opsecScrollObserver = new IntersectionObserver((entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && !opsecScrollLoading) {
            const nextPage = parseInt(sentinel.dataset.nextPage, 10);
            if (nextPage) {
                loadMoreOpsecImages(nextPage, sentinel);
            }
        }
    }, { root: scrollContainer, rootMargin: '600px' });
    opsecScrollObserver.observe(sentinel);
}

async function loadOpsecImages() {
    const list = document.getElementById('opsec-images-list');
    if (!list) return;

    list.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">${window.translations?.loading || 'Loading...'}</div>`;

    try {
        const response = await fetch('/api/opsec-images?page=1&per_page=50');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const images = data.images || [];

        list.innerHTML = '';

        // Update count label
        const countLabel = document.getElementById('opsec-image-count');
        if (countLabel) countLabel.textContent = `(${data.total || images.length})`;

        if (images.length === 0) {
            list.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">${window.translations?.no_opsec_images || 'No OPSec images uploaded yet'}</p>`;
            return;
        }

        images.forEach(img => list.appendChild(createOpsecThumb(img)));

        if (data.has_next) {
            const sentinel = document.createElement('div');
            sentinel.className = 'meme-scroll-sentinel';
            sentinel.dataset.nextPage = data.page + 1;
            list.appendChild(sentinel);
            setupOpsecInfiniteScroll(sentinel);
        }
    } catch (error) {
        console.error('Error loading OPSec images:', error);
        list.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--danger);">Error loading OPSec images</p>`;
    }
}

async function loadMoreOpsecImages(page, sentinel) {
    if (opsecScrollLoading) return;
    opsecScrollLoading = true;
    try {
        const response = await fetch(`/api/opsec-images?page=${page}&per_page=50`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const images = data.images || [];

        if (!images.length) {
            sentinel.remove();
            opsecScrollLoading = false;
            return;
        }

        const list = document.getElementById('opsec-images-list');
        images.forEach(img => list.insertBefore(createOpsecThumb(img), sentinel));

        if (data.has_next) {
            sentinel.dataset.nextPage = page + 1;
        } else {
            if (opsecScrollObserver) opsecScrollObserver.disconnect();
            sentinel.remove();
        }
    } catch (error) {
        console.error('Failed to load more OPSec images:', error);
    }
    opsecScrollLoading = false;
}

function downloadOpsecImage(filename) {
    const a = document.createElement('a');
    a.href = assetUrl('/api/download-opsec/', filename);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

async function deleteOpsecImage(filename) {
    try {
        const response = await fetch(`/api/delete-opsec/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.success) {
            showNotification(window.translations?.opsec_image_deleted_successfully || 'OPSec image deleted successfully!', 'success');
            // Remove from DOM directly to preserve pagination state
            const list = document.getElementById('opsec-images-list');
            if (list) {
                const imgEl = list.querySelector(`img[data-filename="${filename}"]`);
                if (imgEl) {
                    const thumb = imgEl.closest('.meme-thumbnail');
                    if (thumb) thumb.remove();
                    // If grid is now empty (only the load-more btn or nothing left), show empty message
                    const remaining = list.querySelectorAll('.meme-thumbnail');
                    if (remaining.length === 0) {
                        const loadMoreBtn = list.querySelector('.load-more-btn');
                        if (!loadMoreBtn) {
                            list.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">${window.translations?.no_opsec_images || 'No OPSec images uploaded yet'}</p>`;
                        }
                    }
                }
            }
        } else {
            showNotification(result.message || window.translations?.opsec_image_delete_failed || 'Failed to delete OPSec image', 'error');
        }
    } catch (error) {
        showNotification((window.translations?.opsec_image_delete_failed || 'Failed to delete OPSec image') + ': ' + error.message, 'error');
    }
}

function createOpsecManagementInterface(field) {
    const container = document.createElement('div');
    container.className = 'meme-management-container';

    // Upload section
    const uploadSection = document.createElement('div');
    uploadSection.className = 'form-group';
    uploadSection.style.marginBottom = '30px';

    const uploadLabel = document.createElement('label');
    uploadLabel.className = 'form-label';
    uploadLabel.textContent = window.translations?.upload_opsec_image || 'Upload OPSec Cover Image';
    uploadSection.appendChild(uploadLabel);

    const uploadArea = document.createElement('div');
    uploadArea.className = 'upload-area';
    uploadArea.id = 'opsec-upload-area';
    uploadArea.innerHTML = `
        <input type="file" id="opsec-file-input" accept="image/*" multiple style="display: none;">
        <div class="upload-placeholder">
            <img src="/static/icons/add_meme.svg" alt="Add Image" class="upload-icon" style="width: 2rem; height: 2rem; margin-bottom: 10px;" />
            <p>${window.translations?.upload_placeholder || 'Click to select image(s) or drag & drop'}</p>
            <p style="font-size: 0.8rem; color: var(--accent);">${window.translations?.upload_formats || 'Supported: PNG, JPG, JPEG, GIF, WebP (Multiple files allowed)'}</p>
        </div>
    `;

    const uploadProgress = document.createElement('div');
    uploadProgress.id = 'opsec-upload-progress';
    uploadProgress.style.display = 'none';
    uploadProgress.style.marginTop = '10px';
    uploadProgress.innerHTML = `
        <div style="background: var(--bg-input); border-radius: 10px; overflow: hidden;">
            <div id="opsec-progress-bar" style="height: 8px; background: #F7931A; width: 100%; transform: scaleX(0); transform-origin: left; transition: transform 0.3s;"></div>
        </div>
        <p id="opsec-upload-status" style="margin-top: 5px; font-size: 0.9rem;"></p>
    `;

    uploadSection.appendChild(uploadArea);
    uploadSection.appendChild(uploadProgress);

    // Current images section
    const imagesSection = document.createElement('div');
    imagesSection.className = 'form-group';

    const imagesLabel = document.createElement('label');
    imagesLabel.className = 'form-label';
    imagesLabel.innerHTML = `${window.translations?.current_opsec_images || 'Current OPSec Images'} <span id="opsec-image-count" style="color: var(--text-secondary); font-weight: 400;"></span>`;
    imagesSection.appendChild(imagesLabel);

    const imagesList = document.createElement('div');
    imagesList.id = 'opsec-images-list';
    imagesList.style.display = 'grid';
    imagesList.style.gridTemplateColumns = 'repeat(auto-fill, minmax(100px, 1fr))';
    imagesList.style.gap = '10px';
    imagesList.style.marginTop = '10px';

    // Wrap in scrollable container so user can scroll past the section
    const opsecScrollContainer = document.createElement('div');
    opsecScrollContainer.className = 'opsec-scroll-container';
    opsecScrollContainer.appendChild(imagesList);
    imagesSection.appendChild(opsecScrollContainer);

    container.appendChild(uploadSection);
    container.appendChild(imagesSection);

    // Wire up upload area
    setTimeout(() => {
        const area = document.getElementById('opsec-upload-area');
        const fileInput = document.getElementById('opsec-file-input');
        if (!area || !fileInput) return;

        area.addEventListener('click', () => fileInput.click());
        area.addEventListener('dragover', (e) => { e.preventDefault(); area.classList.add('dragover'); });
        area.addEventListener('dragleave', () => area.classList.remove('dragover'));
        area.addEventListener('drop', (e) => {
            e.preventDefault();
            area.classList.remove('dragover');
            uploadOpsecFiles(Array.from(e.dataTransfer.files))
                .catch(err => reportUploadFailure('opsec-upload-status', err));
        });
        fileInput.addEventListener('change', () => {
            uploadOpsecFiles(Array.from(fileInput.files))
                .catch(err => reportUploadFailure('opsec-upload-status', err));
            fileInput.value = '';
        });

        loadOpsecImages();
    }, 100);

    container.getValue = () => null;
    return container;
}

function createDonationHistoryInterface() {
    const container = document.createElement('div');
    container.className = 'donation-history-container';
    container.style.cssText = 'margin-top: 12px;';

    const t = window.translations || {};
    const title = document.createElement('h2');
    title.textContent = t.recent_donations || 'Recent Donations';
    title.style.cssText = 'margin: 0 0 10px 0; font-size: 15px;';
    container.appendChild(title);

    const tableWrapper = document.createElement('div');
    tableWrapper.style.cssText = 'overflow-x: auto; overflow-y: auto; max-height: 210px; border: 1px solid var(--border-color); border-radius: 6px;';

    const table = document.createElement('table');
    table.style.cssText = 'width: 100%; border-collapse: collapse; font-size: 13px;';
    table.innerHTML = `
        <thead>
            <tr style="border-bottom: 1px solid var(--border-color);">
                <th style="text-align:left; padding: 6px 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 1; color: var(--text-secondary);">${t.donation_col_time || 'Time'}</th>
                <th style="text-align:right; padding: 6px 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 1; color: var(--text-secondary); white-space:nowrap;">${t.donation_col_block || 'Block'}</th>
                <th style="text-align:right; padding: 6px 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 1; color: var(--text-secondary);">Sats</th>
                <th style="text-align:left; padding: 6px 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 1; color: var(--text-secondary);">${t.donation_col_message || 'Message'}</th>
            </tr>
        </thead>
        <tbody id="donation-history-tbody"><tr><td colspan="4" style="padding:8px; color: var(--text-muted);">${t.loading || 'Loading…'}</td></tr></tbody>
    `;
    tableWrapper.appendChild(table);
    container.appendChild(tableWrapper);

    // Fixed total row (outside the scrollable wrapper)
    const totalRow = document.createElement('div');
    totalRow.id = 'donation-total-row';
    totalRow.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding: 6px 10px; border: 1px solid var(--border-color); border-top: none; border-radius: 0 0 6px 6px; font-size:13px; background: var(--bg-card);';
    totalRow.innerHTML = `<span style="color:var(--text-secondary);">${t.donation_total || 'Total received'}</span><span id="donation-total-sats" style="font-weight:bold; color:var(--accent); font-family:var(--font-mono);">—</span>`;
    container.appendChild(totalRow);

    // Load donations from API
    fetch('/api/donations')
        .then(r => r.json())
        .then(data => {
            const tbody = table.querySelector('#donation-history-tbody');
            const donations = data.donations || [];
            if (donations.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="padding:8px; color: var(--text-muted);">${t.no_donations_yet || 'No donations yet.'}</td></tr>`;
                return;
            }
            tbody.innerHTML = donations.map(d => {
                const ts = _formatDonationTime(d.timestamp);
                const bh = d.block_height != null ? _fmtNum(d.block_height) : '—';
                const sats = _fmtNum(d.amount_sats || 0);
                const msg = d.message ? escapeHtml(d.message) : '<em style="color: var(--text-muted);">—</em>';
                return `<tr style="border-bottom:1px solid var(--border-color);">
                    <td style="padding:5px 8px; white-space:nowrap;">${ts}</td>
                    <td style="padding:5px 8px; text-align:right; font-family:var(--font-mono); color:var(--text-secondary);">${bh}</td>
                    <td style="padding:5px 8px; text-align:right; font-weight:bold; color:var(--accent); font-family:var(--font-mono);">${sats}</td>
                    <td style="padding:5px 8px;">${msg}</td>
                </tr>`;
            }).join('');
            const total = donations.reduce((sum, d) => sum + (d.amount_sats || 0), 0);
            const totalEl = container.querySelector('#donation-total-sats');
            if (totalEl) {
                totalEl.dataset.total = total;
                totalEl.textContent = _fmtNum(total) + ' sats';
            }
        })
        .catch(() => {
            const tbody = table.querySelector('#donation-history-tbody');
            tbody.innerHTML = `<tr><td colspan="4" style="padding:8px; color: var(--text-muted);">${t.could_not_load_donations || 'Could not load donations.'}</td></tr>`;
        });

    container.getValue = () => null;
    return container;
}

function escapeHtml(text) {
    return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
