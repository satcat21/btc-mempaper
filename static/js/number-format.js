// Browser-side mirror of utils/number_format.py.
//
// Loaded by every page that prints a figure, so the config page, the dashboard
// and the rendered display all punctuate the same number the same way. Before
// this existed each page decided for itself: the config page followed the
// browser's locale via toLocaleString, the dashboard hardcoded dots, and the
// renderer followed the setting - so one device could show 62,923 in a toast,
// 62.923 on the panel and either one in a preview claiming to show the panel.
//
// The setting arrives differently per page: the config page has the whole
// config in window.currentConfig (plus unsaved edits in _pendingConfigOverrides,
// which must win so a preview updates before a save), while the dashboard gets
// only this one value injected as window.numberFormat.

function _numStyle() {
    const pending = window._pendingConfigOverrides || {};
    const cfg = window.currentConfig || {};
    const v = pending.number_format ?? cfg.number_format ?? window.numberFormat;
    return v === 'us' ? 'us' : 'eu';
}

function _decMark() { return _numStyle() === 'us' ? '.' : ','; }

function _fmtNum(n, decimals = 0) {
    if (n == null || isNaN(n)) return '—';
    // en-US gives the grouped form; EU is that with the two marks swapped.
    const s = Number(n).toLocaleString('en-US', {
        minimumFractionDigits: decimals, maximumFractionDigits: decimals,
    });
    return _numStyle() === 'us' ? s : s.replace(/[.,]/g, (c) => (c === ',' ? '.' : ','));
}

// Repoint an already-fixed decimal such as toFixed(8), where there is no grouping.
function _fmtFixed(n, decimals) {
    if (n == null || isNaN(n)) return '—';
    const s = Number(n).toFixed(decimals);
    return _numStyle() === 'us' ? s : s.replace('.', ',');
}

// Mirrors FormattingMixin._format_fee: whole numbers stay whole, a tenth below
// 10 sat/vB, three decimals below 0.1 so a relay minimum is not rounded away.
function _fmtFee(v) {
    const n = Number(v);
    if (v == null || isNaN(n)) return String(v);
    if (n >= 10 || Number.isInteger(n)) return _fmtNum(Math.round(n));
    if (n >= 0.1) return _fmtFixed(n, 1);
    return _fmtFixed(n, 3).replace(/0+$/, '');
}
