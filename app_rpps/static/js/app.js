/**
 * Sistema RPPS - JavaScript Principal
 * Centraliza toda a lógica JavaScript do sistema
 */

// ============================================================================
// MÓDULO: Máscaras de Documentos (CPF/CNPJ)
// ============================================================================
const DocumentoMask = {
    /**
     * Formata CPF ou CNPJ automaticamente durante a digitação
     */
    formatarDocumento(valor) {
        valor = valor.replace(/\D/g, '');
        
        // CPF: 000.000.000-00 (11 dígitos)
        if (valor.length <= 11) {
            if (valor.length > 9) {
                return valor.replace(/(\d{3})(\d{3})(\d{3})(\d{1,2})/, '$1.$2.$3-$4');
            } else if (valor.length > 6) {
                return valor.replace(/(\d{3})(\d{3})(\d{1,3})/, '$1.$2.$3');
            } else if (valor.length > 3) {
                return valor.replace(/(\d{3})(\d{1,3})/, '$1.$2');
            }
            return valor;
        }
        
        // CNPJ: 00.000.000/0000-00 (14 dígitos)
        if (valor.length <= 14) {
            if (valor.length > 12) {
                return valor.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{1,2})/, '$1.$2.$3/$4-$5');
            } else if (valor.length > 8) {
                return valor.replace(/(\d{2})(\d{3})(\d{3})(\d{1,4})/, '$1.$2.$3/$4');
            } else if (valor.length > 5) {
                return valor.replace(/(\d{2})(\d{3})(\d{1,3})/, '$1.$2.$3');
            } else if (valor.length > 2) {
                return valor.replace(/(\d{2})(\d{1,3})/, '$1.$2');
            }
            return valor;
        }
        
        // Limita a 14 dígitos
        valor = valor.slice(0, 14);
        return valor.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
    },

    /**
     * Inicializa as máscaras nos campos
     */
    init() {
        document.querySelectorAll('input[data-mask-cpfcnpj="true"]').forEach(input => {
            // Guarda a posição do cursor
            let lastCursorPosition = 0;
            
            input.addEventListener('input', function(e) {
                // Salva posição do cursor
                const cursorPos = this.selectionStart;
                const valorAnterior = this.value;
                
                // Remove tudo que não é número
                let valor = this.value.replace(/\D/g, '');
                
                // Limita a 14 dígitos
                if (valor.length > 14) {
                    valor = valor.slice(0, 14);
                }
                
                // Aplica formatação
                const formatado = DocumentoMask.formatarDocumento(valor);
                
                // Atualiza o valor apenas se mudou
                if (formatado !== this.value) {
                    this.value = formatado;
                    
                    // Ajusta a posição do cursor
                    const diff = formatado.length - valorAnterior.length;
                    const newCursorPos = cursorPos + diff;
                    this.setSelectionRange(newCursorPos, newCursorPos);
                }
            });

            // Validação no blur
            input.addEventListener('blur', function() {
                const valor = this.value.replace(/\D/g, '');
                
                // Se tiver valor mas não for 11 ou 14 dígitos, limpa
                if (valor.length > 0 && valor.length !== 11 && valor.length !== 14) {
                    this.value = '';
                    this.classList.add('is-invalid');
                } else if (valor.length > 0) {
                    this.value = DocumentoMask.formatarDocumento(valor);
                    this.classList.remove('is-invalid');
                }
            });

            // Permite colar com Ctrl+V
            input.addEventListener('paste', function(e) {
                e.preventDefault();
                const pastedText = (e.clipboardData || window.clipboardData).getData('text');
                const valor = pastedText.replace(/\D/g, '');
                this.value = DocumentoMask.formatarDocumento(valor);
            });
        });

        // Trata mudanças programáticas (ex: transferência via modal) que disparam 'change'
        // Formata o valor e re-dispara um evento 'input' para que outras rotinas (ex: validação)
        // também sejam executadas. Colocado aqui para garantir que o handler exista quando
        // o módulo for inicializado.
        document.addEventListener('change', function(e) {
            const el = e.target;
            if (!el) return;
            if (el.matches && el.matches('input[data-mask-cpfcnpj="true"]')) {
                const raw = el.value.replace(/\D/g, '');

                if (raw.length === 11 || raw.length === 14) {
                    const formatted = DocumentoMask.formatarDocumento(raw);
                    if (formatted !== el.value) {
                        el.value = formatted;
                    }
                    el.classList.remove('is-invalid');

                    // Re-dispara 'input' para que listeners que escutam por 'input' reajam
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                } else if (raw.length > 0) {
                    // valor inválido: limpa e marca erro
                    el.value = '';
                    el.classList.add('is-invalid');
                }
            }
        });
    }
};

// ============================================================================
// MÓDULO: Navegação por Teclado
// ============================================================================
const FormNavigation = {
    /**
     * Encontra o próximo elemento focável (apenas inputs, selects, textareas)
     */
    getNextFocusableElement(currentElement) {
        const focusableElements = 'input:not([type="hidden"]), select, textarea';
        const form = document.getElementById('dynamic-form');
        if (!form) return null;
        
        const elements = Array.from(form.querySelectorAll(focusableElements))
            .filter(el => !el.disabled && !el.readOnly && getComputedStyle(el).display !== 'none');
        
        const currentIndex = elements.indexOf(currentElement);
        return elements[currentIndex + 1] || null;
    },

    /**
     * Define foco no primeiro campo ao carregar APENAS se não for reload de submissão
     */
    setInitialFocus() {
        const form = document.getElementById('dynamic-form');
        if (!form) return;
        
        // Não focar automaticamente se a página foi recarregada por submissão
        if (performance.navigation && performance.navigation.type === 1) {
            return;
        }
        
        // Não focar se vier de uma submissão POST
        const isFromSubmission = document.referrer && document.referrer === window.location.href;
        if (isFromSubmission) return;
        
        // Encontra o primeiro input visível e editável
        const firstInput = form.querySelector('input:not([type="hidden"]):not([readonly]):not([disabled]), select:not([disabled]), textarea:not([readonly]):not([disabled])');
        if (firstInput) {
            setTimeout(() => {
                firstInput.focus();
                if (firstInput.tagName.toLowerCase() === 'input') {
                    firstInput.select();
                }
            }, 100);
        }
    },

    /**
     * Inicializa navegação por teclado
     */
    init() {
        const form = document.getElementById('dynamic-form');
        if (!form) return;

        // Define foco inicial APENAS uma vez no carregamento
        this.setInitialFocus();

        // Previne Enter de submeter e move para próximo campo
        form.querySelectorAll('input, select, textarea').forEach(input => {
            input.addEventListener('keydown', function(e) {
                // Apenas para Enter e não em textarea
                if (e.key === 'Enter' && this.tagName.toLowerCase() !== 'textarea') {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Verifica se está em campo de chave com botão de pesquisa
                    const inputGroup = this.closest('.input-group');
                    if (inputGroup && inputGroup.querySelector('button.btn-pesquisa')) {
                        // Clica no botão de pesquisa
                        const btnPesquisa = inputGroup.querySelector('button.btn-pesquisa');
                        if (btnPesquisa) {
                            btnPesquisa.click();
                        }
                        return false;
                    }
                    
                    // Move para o próximo campo
                    const nextElement = FormNavigation.getNextFocusableElement(this);
                    if (nextElement) {
                        nextElement.focus();
                        if (nextElement.tagName.toLowerCase() === 'input') {
                            nextElement.select();
                        }
                    }
                    
                    return false;
                }
            });
        });

        // Desabilita hx-trigger nos campos com blur quando usar Enter
        form.querySelectorAll('input[hx-trigger*="blur"]').forEach(input => {
            // Remove blur trigger e adiciona apenas change explícito
            const originalTrigger = input.getAttribute('hx-trigger');
            if (originalTrigger && originalTrigger.includes('blur')) {
                // Substitui blur por focusout para evitar disparo no Tab
                input.setAttribute('hx-trigger', 'change from:body');
            }
        });
    }
};

// ============================================================================
// MÓDULO: Validação de Formulários
// ============================================================================
const FormValidation = {
    /**
     * Inicializa validação de formulários
     */
    init() {
        const form = document.getElementById('dynamic-form');
        if (!form) return;

        form.addEventListener('submit', function(e) {
            const submitButton = document.activeElement;
            
            // Não valida se for botão de excluir
            if (submitButton && submitButton.value !== 'excluir') {
                if (!this.checkValidity()) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const firstInvalidField = this.querySelector(':invalid');
                    if (firstInvalidField) {
                        firstInvalidField.focus();
                    }
                }
            }
            
            this.classList.add('was-validated');
        });
    }
};

// ============================================================================
// MÓDULO: Modais e HTMX
// ============================================================================
const ModalManager = {
    /**
     * Inicializa gerenciamento de modais
     */
    init() {
        // Handler para HTMX afterSwap
        document.body.addEventListener('htmx:afterSwap', function(evt) {
            const target = evt.detail?.target;
            console.log('[MODAL] HTMX afterSwap - Target:', target?.id, 'Classes:', target?.className);
            
            if (!target) {
                console.log('[MODAL] Sem target, abortando');
                return;
            }

            if (target.id === 'modal' || target.classList.contains('modal')) {
                console.log('[MODAL] Target é modal, verificando conteúdo...');
                
                if (!target.innerHTML || target.innerHTML.trim() === '') {
                    console.log('[MODAL] Modal vazio, abortando');
                    return;
                }

                console.log('[MODAL] Tentando abrir modal...');
                let modalInst = null;
                if (bootstrap?.Modal?.getOrCreateInstance) {
                    modalInst = bootstrap.Modal.getOrCreateInstance(target);
                } else if (bootstrap?.Modal?.getInstance) {
                    modalInst = bootstrap.Modal.getInstance(target) || new bootstrap.Modal(target);
                }

                if (modalInst && typeof modalInst.show === 'function') {
                    console.log('[MODAL] Abrindo modal com sucesso!');
                    modalInst.show();
                } else {
                    console.error('[MODAL] Erro: Não foi possível criar instância do modal');
                }
            } else {
                console.log('[MODAL] Target não é modal, ignorando');
            }
        });

        // Limpa modal ao fechar
        const modalElements = document.querySelectorAll('.modal');
        modalElements.forEach(modalEl => {
            modalEl.addEventListener('hidden.bs.modal', function() {
                this.innerHTML = '';
            });
        });

        // Listener para fechar o modal e reinicializar os scripts após a transferência
        document.body.addEventListener('formAtualizado', function() {
            // 1. Fecha o modal
            const modalEl = document.getElementById('modal');
            if (modalEl) {
                const modalInst = bootstrap.Modal.getInstance(modalEl);
                if (modalInst) {
                    modalInst.hide();
                }
            }

            // 2. Re-inicializa os módulos para o novo formulário
            // Usa setTimeout para garantir que o DOM foi atualizado
            setTimeout(() => {
                if (window.RPPS) {
                    console.log('[formAtualizado] Reinicializando módulos JS...');
                    window.RPPS.DocumentoMask.init();
                    window.RPPS.FormNavigation.init();
                    window.RPPS.FormValidation.init();
                    console.log('[formAtualizado] Módulos JS reinicializados.');
                }
            }, 100);
        });
    }
};

// ============================================================================
// MÓDULO: Relatórios
// ============================================================================
const ReportManager = {
    /**
     * Inicializa gerenciamento de relatórios
     */
    init() {
        const reportModal = document.getElementById('reportModal');
        if (!reportModal) return;

        reportModal.addEventListener('show.bs.modal', function() {
            const modalBody = document.getElementById('reportModalBody');
            const form = document.getElementById('dynamic-form');
            if (!form) return;

            const actionUrl = form.getAttribute('action');
            const tabelaMatch = actionUrl?.match(/tratamento\/([^\/]+)/);
            if (!tabelaMatch) return;

            const tabela = tabelaMatch[1];
            const queryParams = new URLSearchParams();
            
            Array.from(form.elements).forEach(element => {
                if (element.name && element.value) {
                    queryParams.append(element.name, element.value);
                }
            });

            const reportUrl = `/relatorio/${tabela}/?${queryParams.toString()}`;
            const excelUrl = `/export/excel/${tabela}/?${queryParams.toString()}`;
            const pdfUrl = `/export/pdf/${tabela}/?${queryParams.toString()}`;

            const excelBtn = document.getElementById('export-excel-btn');
            const pdfBtn = document.getElementById('export-pdf-btn');
            if (excelBtn) excelBtn.href = excelUrl;
            if (pdfBtn) pdfBtn.href = pdfUrl;

            modalBody.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"><span class="visually-hidden">Carregando...</span></div></div>';
            
            fetch(reportUrl)
                .then(response => response.text())
                .then(html => {
                    modalBody.innerHTML = html;
                })
                .catch(error => {
                    console.error('Error loading report:', error);
                    modalBody.innerHTML = '<div class="alert alert-danger">Erro ao carregar o relatório.</div>';
                });
        });
    }
};

// ============================================================================
// MÓDULO: Saudação
// ============================================================================
const GreetingManager = {
    /**
     * Atualiza saudação do usuário
     */
    init() {
        const saudacao = document.getElementById('saudacao');
        if (!saudacao) return;

        const nomeUsuario = saudacao.dataset.username || '';
        const hora = new Date().getHours();
        let mensagem = 'Olá';

        if (hora >= 5 && hora < 12) {
            mensagem = 'Bom dia';
        } else if (hora >= 12 && hora < 18) {
            mensagem = 'Boa tarde';
        } else {
            mensagem = 'Boa noite';
        }

        saudacao.textContent = `${mensagem}, ${nomeUsuario}`;
    }
};

const BlurManager = {
    init() {
        const form = document.getElementById('dynamic-form');
        if (!form) return;

        const campos = form.querySelectorAll('[data-campo-blur="true"]');
        if (!campos.length) return;

        campos.forEach(campo => {
            if (campo.dataset.blurInitialized === 'true') return;
            campo.dataset.blurInitialized = 'true';

            campo.addEventListener('blur', function() {
                const checkUrl = this.getAttribute('data-check-url');
                const camposRelacionados = this.getAttribute('data-campos-relacionados');
                if (!checkUrl) return;

                const related = (camposRelacionados || '')
                    .split(',')
                    .map(item => item.trim())
                    .filter(Boolean);

                const requiredKeys = Array.from(new Set([...related, this.name]));
                const missing = requiredKeys.filter(nome => {
                    const el = form.querySelector(`[name="${nome}"]`);
                    const value = ((el && el.value) || '').trim();
                    return !value || value === '0';
                });

                if (missing.length) {
                    console.log(`[PK_BLUR] Aguardando chave completa. Faltando: ${missing.join(', ')}`);
                    return;
                }

                const params = new URLSearchParams();
                const appended = new Set();
                requiredKeys.forEach(nome => {
                    const el = form.querySelector(`[name="${nome}"]`);
                    if (!el) return;
                    const value = (el.value || '').trim();
                    if (!value || value === '0' || appended.has(nome)) return;
                    params.append(nome, value);
                    appended.add(nome);
                });

                const fullUrl = `${checkUrl}?${params.toString()}`;
                console.log(`[PK_BLUR] Disparando blur-check: ${this.name} -> ${fullUrl}`);

                fetch(fullUrl, {
                    headers: {
                        'HX-Request': 'true',
                        'Accept': 'text/html'
                    }
                })
                    .then(response => response.text())
                    .then(html => {
                        const parser = new DOMParser();
                        const doc = parser.parseFromString(html, 'text/html');
                        const newForm = doc.querySelector('form#dynamic-form');
                        if (newForm) {
                            const currentForm = document.getElementById('dynamic-form');
                            if (currentForm) {
                                currentForm.replaceWith(newForm);
                            }
                            console.log(`[PK_BLUR] Form atualizdo via chave composta em "${this.name}"`);
                        }
                    })
                    .catch(error => {
                        console.error('[PK_BLUR] Falha no blur-check:', error);
                    });
            });
        });
    }
};

// ============================================================================
// INICIALIZAÇÃO GLOBAL
// ============================================================================
document.addEventListener('DOMContentLoaded', function() {
    // Inicializa todos os módulos
    DocumentoMask.init();
    FormNavigation.init();
    FormValidation.init();
    ModalManager.init();
    ReportManager.init();
    GreetingManager.init();
    BlurManager.init();
});

// Exporta módulos para uso global se necessário
window.RPPS = {
    DocumentoMask,
    FormNavigation,
    FormValidation,
    ModalManager,
    ReportManager,
    GreetingManager,
    BlurManager
};
