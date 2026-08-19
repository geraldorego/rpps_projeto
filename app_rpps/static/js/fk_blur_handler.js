// ===============================================
//  fk_blur_handler.js
//  Autor: Gjota / RPPS_APP
//  Objetivo: Buscar dados ao sair de campos FK
// ===============================================

document.addEventListener('DOMContentLoaded', function () {
    console.log('[FK_BLUR] Handler carregado');
    
    initFkBlurHandlers();
});

// Reinicializa após HTMX swap
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target && evt.detail.target.id === 'dynamic-form') {
        console.log('[FK_BLUR] Reinicializando após HTMX swap');
        initFkBlurHandlers();
    }
});

function initFkBlurHandlers() {
    // Busca todos os campos que têm data-tabela-ref (campos FK)
    const camposFk = document.querySelectorAll('[data-tabela-ref]');
    
    console.log(`[FK_BLUR] Encontrados ${camposFk.length} campos FK`);
    
    camposFk.forEach(campoFk => {
        // Remove listeners antigos para evitar duplicação
        const newCampo = campoFk.cloneNode(true);
        campoFk.parentNode.replaceChild(newCampo, campoFk);
        
        newCampo.addEventListener('blur', function() {
            handleFkBlur(this);
        });
        
        console.log(`[FK_BLUR] Listener adicionado em: ${newCampo.name}`);
    });
}

function handleFkBlur(campo) {
    const nomeCampo = campo.name;
    const valor = campo.value.trim();
    const tabelaRef = campo.dataset.tabelaRef;
    const fieldMapping = campo.dataset.fieldMapping;
    const isPkBlur = campo.dataset.campoBlur === 'true';
    
    // Se o campo também é o último da PK (data-campo-blur="true"),
    // priorizamos o check da PK para carregar o registro inteiro (CRUD)
    if (isPkBlur) {
        console.log(`[FK_BLUR] Campo ${nomeCampo} também é PK blur — priorizando check_record (ignorado aqui).`);
        return;
    }

    console.log(`[FK_BLUR] Blur em: ${nomeCampo}, valor: ${valor}`);
    
    if (!valor) {
        console.log('[FK_BLUR] Campo vazio, ignorando');
        return;
    }
    
    if (!tabelaRef) {
        console.log('[FK_BLUR] Sem tabela de referência, ignorando');
        return;
    }
    
    // Pega o nome da tabela atual da URL
    const pathParts = window.location.pathname.split('/');
    const tabela = pathParts[1]; // Ex: /MembroColegio/ -> MembroColegio
    
    if (!tabela) {
        console.error('[FK_BLUR] Não foi possível identificar a tabela');
        return;
    }
    
    // Monta a URL da API
    const url = `/${tabela}/check-fk/${nomeCampo}/?${nomeCampo}=${encodeURIComponent(valor)}`;
    
    console.log(`[FK_BLUR] Buscando em: ${url}`);
    
    // Feedback visual
    campo.style.border = '2px solid #0d6efd';
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            console.log('[FK_BLUR] Resposta recebida:', data);
            
            if (data.found && data.data) {
                // Preenche os campos relacionados
                let preenchidos = 0;
                for (const [campoLocal, valorRef] of Object.entries(data.data)) {
                    const inputLocal = document.querySelector(`[name="${campoLocal}"]`);
                    if (inputLocal) {
                        inputLocal.value = valorRef;
                        inputLocal.style.backgroundColor = '#d4edda'; // Verde claro
                        setTimeout(() => {
                            inputLocal.style.backgroundColor = '';
                        }, 2000);
                        preenchidos++;
                        console.log(`[FK_BLUR] ✅ Preenchido: ${campoLocal} = ${valorRef}`);
                    } else {
                        console.warn(`[FK_BLUR] ⚠️ Campo ${campoLocal} não encontrado no formulário`);
                    }
                }
                
                if (preenchidos > 0) {
                    campo.style.border = '2px solid #28a745'; // Verde
                    // Mostra mensagem de sucesso
                    showToast('success', `${preenchidos} campo(s) preenchido(s) automaticamente`);
                } else {
                    campo.style.border = '2px solid #ffc107'; // Amarelo
                    showToast('warning', 'Registro encontrado mas nenhum campo foi mapeado');
                }
            } else {
                campo.style.border = '2px solid #ffc107'; // Amarelo
                showToast('info', data.message || 'Registro não encontrado');
            }
            
            setTimeout(() => {
                campo.style.border = '';
            }, 2000);
        })
        .catch(error => {
            console.error('[FK_BLUR] Erro:', error);
            campo.style.border = '2px solid #dc3545'; // Vermelho
            showToast('error', 'Erro ao buscar dados');
            setTimeout(() => {
                campo.style.border = '';
            }, 2000);
        });
}

function showToast(type, message) {
    // Implementação simples de toast
    const toast = document.createElement('div');
    toast.style.position = 'fixed';
    toast.style.top = '20px';
    toast.style.right = '20px';
    toast.style.padding = '15px 20px';
    toast.style.borderRadius = '5px';
    toast.style.zIndex = '9999';
    toast.style.fontWeight = 'bold';
    toast.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
    
    const colors = {
        success: { bg: '#d4edda', text: '#155724', border: '#c3e6cb' },
        warning: { bg: '#fff3cd', text: '#856404', border: '#ffeaa7' },
        info: { bg: '#d1ecf1', text: '#0c5460', border: '#bee5eb' },
        error: { bg: '#f8d7da', text: '#721c24', border: '#f5c6cb' }
    };
    
    const color = colors[type] || colors.info;
    toast.style.backgroundColor = color.bg;
    toast.style.color = color.text;
    toast.style.border = `1px solid ${color.border}`;
    
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}
