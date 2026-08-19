// ===============================================
//  campo_blur_handler.js
//  Autor: Gjota / RPPS_APP
//  Versão: 2025.10.29
//  Objetivo: Executar checagem automática via blur
//  com realce de campos, debounce e integração HTMX
// ===============================================

document.addEventListener('DOMContentLoaded', function () {
    if (window.RPPS && typeof window.RPPS.BlurManager?.init === 'function') {
        window.RPPS.BlurManager.init();
    }
});

document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target && evt.detail.target.id === 'dynamic-form') {
        if (window.RPPS && typeof window.RPPS.BlurManager?.init === 'function') {
            window.RPPS.BlurManager.init();
        }
    }
});
