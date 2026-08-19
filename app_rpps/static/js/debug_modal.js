// Script temporário para debug do modal
document.addEventListener('DOMContentLoaded', function() {
    console.log('=== DEBUG MODAL INICIADO ===');
    
    // Inicializa flag de submit
    window._formCanSubmit = false;
    
    // Monitora cliques em botões de pesquisa
    document.body.addEventListener('click', function(e) {
        const btn = e.target.closest('button.btn-pesquisa');
        if (btn) {
            console.log('✓ Botão pesquisa clicado');
            console.log('  - HTMX disponível:', typeof htmx !== 'undefined');
            console.log('  - hx-get:', btn.getAttribute('hx-get'));
            console.log('  - hx-target:', btn.getAttribute('hx-target'));
            console.log('  - type:', btn.type);
            
            // Garante que não submete o form
            window._formCanSubmit = false;
        }
    }, true);
    
    // Monitora submit do form
    const form = document.getElementById('dynamic-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!window._formCanSubmit) {
                console.warn('⚠ Submit bloqueado (não intencional)');
                e.preventDefault();
                return false;
            }
            console.log('✓ Submit permitido');
            window._formCanSubmit = false; // Reset
        });
    }
    
    // Monitora eventos HTMX
    if (typeof htmx !== 'undefined') {
        document.body.addEventListener('htmx:beforeRequest', function(e) {
            console.log('✓ HTMX beforeRequest', e.detail.path);
        });
        
        document.body.addEventListener('htmx:afterSwap', function(e) {
            console.log('✓ HTMX afterSwap');
            const modal = document.getElementById('modal');
            if (modal) {
                console.log('  - Conteúdo do modal:', modal.innerHTML.length, 'caracteres');
            }
        });
        
        document.body.addEventListener('htmx:responseError', function(e) {
            console.error('✗ HTMX responseError:', e.detail);
        });
        
        document.body.addEventListener('htmx:sendError', function(e) {
            console.error('✗ HTMX sendError:', e.detail);
        });
    } else {
        console.error('✗ HTMX não disponível!');
    }
});
