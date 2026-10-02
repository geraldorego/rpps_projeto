/**
 * Sistema de Preenchimento Automático de Campos Relacionados via FK
 * 
 * Funcionalidades:
 * 1. Detecta mudança em campos FK (select2)
 * 2. Busca dados da tabela referenciada via AJAX
 * 3. Preenche campos locais conforme mapeamento configurado
 * 4. Adiciona botão de manutenção CRUD para tabela referenciada
 */

(function() {
    'use strict';

    // Configuração global armazenada no contexto do template
    window.FK_RELATED_CONFIG = window.FK_RELATED_CONFIG || {};

    /**
     * Inicializa o sistema de campos relacionados
     */
    function initFKRelatedFields() {
        console.log('[FK_RELATED] Inicializando sistema de campos relacionados...');

        // Aguarda carregamento completo do DOM
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupFieldListeners);
        } else {
            setupFieldListeners();
        }
    }

    /**
     * Configura listeners para campos FK
     */
    function setupFieldListeners() {
        const fkFields = document.querySelectorAll('[data-fk-field]');

        if (fkFields.length === 0) {
            console.log('[FK_RELATED] Nenhum campo FK com mapeamento encontrado');
            return;
        }

        console.log(`[FK_RELATED] Configurando ${fkFields.length} campos FK`);

        const hasJQuery = typeof window.jQuery !== 'undefined' && typeof window.$ !== 'undefined';

        fkFields.forEach(field => {
            // Compartilha a trava com main.js para evitar listeners e AJAX duplicados.
            if (field.dataset.appRppsRelatedBound === 'true') return;
            field.dataset.appRppsRelatedBound = 'true';

            const fieldName = field.getAttribute('data-fk-field');
            const tabelaReferencia = field.getAttribute('data-tabela-ref');
            const fieldMapping = field.getAttribute('data-field-mapping');

            console.log(`[FK_RELATED] Campo: ${fieldName}, Tabela Ref: ${tabelaReferencia}`);

            // Para Select2 (somente se jQuery estiver disponível)
            if (hasJQuery && (window.$(field).hasClass('select2') || window.$(field).data('select2'))) {
                window.$(field).on('select2:select', function(e) {
                    handleFKChange(field, e.params.data.id, fieldName, fieldMapping);
                });
            }
            // Para select padrão
            else if (field.tagName === 'SELECT') {
                field.addEventListener('change', function() {
                    if (this.value) {
                        handleFKChange(field, this.value, fieldName, fieldMapping);
                    }
                });
            }

            // Adiciona botão de manutenção CRUD se houver tabela de referência
            if (tabelaReferencia) {
                addCRUDButton(field, tabelaReferencia);
            }
        });
    }

    /**
     * Manipula mudança no campo FK
     */
    function handleFKChange(field, fkId, fieldName, fieldMapping) {
        if (!fkId || !fieldMapping) {
            console.log('[FK_RELATED] ID da FK ou mapeamento não fornecido');
            return;
        }

        const requestedValue = String(fkId);
        let requestedValues = [];
        try {
            requestedValues = JSON.parse(field.dataset.appRppsRelatedRequestedValues || '[]');
        } catch (error) {
            requestedValues = [];
        }
        if (requestedValues.includes(requestedValue)) return;
        requestedValues.push(requestedValue);
        field.dataset.appRppsRelatedRequestedValues = JSON.stringify(requestedValues);

        console.log(`[FK_RELATED] Mudança detectada em ${fieldName}: FK ID = ${fkId}`);

        // Obtém tabela principal do formulário
        const tabelaElement = document.querySelector('[data-tabela]');
        const tabela = tabelaElement ? tabelaElement.getAttribute('data-tabela') : null;
        if (!tabela) {
            console.error('[FK_RELATED] Tabela principal não encontrada');
            return;
        }

        // Monta URL do endpoint
        const url = `/api/related-fields/${tabela}/${fieldName}/?fk_id=${fkId}`;

        // Mostra indicador de carregamento
        showLoadingIndicator(field);

        // Busca dados via AJAX
        fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                hideLoadingIndicator(field);

                if (String(field.value || '') === requestedValue && data.success && data.data) {
                    console.log('[FK_RELATED] Dados recebidos:', data.data);
                    fillRelatedFields(data.data, field);
                } else {
                    console.warn('[FK_RELATED] Resposta sem dados:', data);
                }
            })
            .catch(error => {
                hideLoadingIndicator(field);
                console.error('[FK_RELATED] Erro ao buscar dados:', error);

                // Exibe mensagem de erro amigável
                showErrorMessage(`Erro ao buscar dados relacionados: ${error.message}`);
            });
    }

    /**
     * Preenche campos locais com dados da referência
     */
    function fillRelatedFields(data, sourceField) {
        Object.entries(data).forEach(([localField, value]) => {
            const targetField = document.querySelector(`[name="${localField}"]`) ||
                document.getElementById(`id_${localField}`);

            if (targetField && targetField !== sourceField) {
                // Limpa valor anterior
                const nextValue = value == null ? '' : String(value);
                if (String(targetField.value || '') === nextValue) return;
                targetField.value = nextValue;

                // Dispara evento de mudança para atualizar validações
                targetField.dispatchEvent(new Event('change', { bubbles: true }));

                // Adiciona feedback visual
                highlightField(targetField);

                console.log(`[FK_RELATED] Campo ${localField} preenchido com: ${value}`);
            } else {
                console.warn(`[FK_RELATED] Campo ${localField} não encontrado no formulário`);
            }
        });
    }

    /**
     * Adiciona botão de manutenção CRUD ao lado do campo FK
     */
    function addCRUDButton(field, tabelaReferencia) {
        // Evita duplicação
        const existingBtn = field.parentElement.querySelector('.btn-crud-manutencao');
        if (existingBtn) return;

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-sm btn-outline-primary btn-crud-manutencao ms-2';
        button.innerHTML = '<i class="bi bi-pencil-square"></i> Manutenção';
        button.title = `Abrir CRUD de ${tabelaReferencia}`;
        button.setAttribute('data-tabela-ref', tabelaReferencia);

        button.addEventListener('click', function() {
            openCRUDModal(tabelaReferencia);
        });

        // Insere o botão após o campo (ou após o wrapper do Select2)
        const wrapper = field.closest('.form-group') || field.parentElement;
        const insertTarget = field.nextElementSibling && field.nextElementSibling.classList.contains('select2') ?
            field.nextElementSibling : field;

        insertTarget.parentNode.insertBefore(button, insertTarget.nextSibling);

        console.log(`[FK_RELATED] Botão CRUD adicionado para ${tabelaReferencia}`);
    }

    /**
     * Abre modal para CRUD da tabela referenciada
     */
    function openCRUDModal(tabelaReferencia) {
        console.log(`[FK_RELATED] Abrindo modal CRUD para ${tabelaReferencia}`);

        // Cria modal Bootstrap dinamicamente
        const modalId = 'crudModal';
        let modal = document.getElementById(modalId);

        if (!modal) {
            modal = createCRUDModal(modalId, tabelaReferencia);
            document.body.appendChild(modal);
        }

        // Carrega conteúdo via HTMX
        const modalBody = modal.querySelector('.modal-body');
        modalBody.innerHTML = '<div class="text-center p-4"><div class="spinner-border" role="status"></div><p class="mt-2">Carregando formulário...</p></div>';

        // URL do formulário CRUD
        const url = `/${tabelaReferencia}/`;

        // Usa fetch para carregar o form
        fetch(url)
            .then(response => response.text())
            .then(html => {
                // Extrai apenas o formulário do HTML completo
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const formContent = doc.querySelector('.container') || doc.body;

                modalBody.innerHTML = formContent.innerHTML;

                // Re-inicializa scripts necessários (Select2, máscaras, etc)
                reinitializeFormScripts(modalBody);
            })
            .catch(error => {
                modalBody.innerHTML = `<div class="alert alert-danger">Erro ao carregar formulário: ${error.message}</div>`;
            });

        // Mostra o modal
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();

        // Atualiza campo FK ao fechar modal (caso tenha criado novo registro)
        modal.addEventListener('hidden.bs.modal', function() {
            refreshFKField(tabelaReferencia);
        });
    }

    /**
     * Cria estrutura HTML do modal CRUD
     */
    function createCRUDModal(modalId, tabelaReferencia) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = modalId;
        modal.tabIndex = -1;
        modal.innerHTML = `
            <div class="modal-dialog modal-xl modal-dialog-scrollable">
                <div class="modal-content">
                    <div class="modal-header bg-primary text-white">
                        <h5 class="modal-title">
                            <i class="bi bi-pencil-square"></i> 
                            Manutenção: ${tabelaReferencia}
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <!-- Conteúdo carregado dinamicamente -->
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Fechar</button>
                    </div>
                </div>
            </div>
        `;
        return modal;
    }

    /**
     * Re-inicializa scripts do formulário dentro do modal
     */
    function reinitializeFormScripts(container) {
        // Select2
        if (typeof $ !== 'undefined' && $.fn.select2) {
            $(container).find('select.form-select').each(function() {
                if (!$(this).hasClass('select2-hidden-accessible')) {
                    $(this).select2({
                        theme: 'bootstrap-5',
                        width: '100%',
                        dropdownParent: $(container)
                    });
                }
            });
        }

        // Máscaras de documento
        if (typeof aplicarMascaraDocumento === 'function') {
            container.querySelectorAll('[data-mask="documento"]').forEach(aplicarMascaraDocumento);
        }

        console.log('[FK_RELATED] Scripts do formulário re-inicializados');
    }

    /**
     * Atualiza campo FK após fechar modal (recarrega opções)
     */
    function refreshFKField(tabelaReferencia) {
        console.log(`[FK_RELATED] Atualizando campos FK de ${tabelaReferencia}`);

        // Encontra todos os campos FK que referenciam esta tabela
        const fkFields = document.querySelectorAll(`[data-tabela-ref="${tabelaReferencia}"]`);

        fkFields.forEach(field => {
            if ($(field).hasClass('select2-hidden-accessible')) {
                // Para Select2, recarrega as opções
                $(field).trigger('change.select2');
            }
        });
    }

    /**
     * Feedback visual - destaca campo preenchido
     */
    function highlightField(field) {
        field.classList.add('border-success', 'border-2');
        setTimeout(() => {
            field.classList.remove('border-success', 'border-2');
        }, 2000);
    }

    /**
     * Mostra indicador de carregamento
     */
    function showLoadingIndicator(field) {
        const wrapper = field.closest('.form-group') || field.parentElement;
        let indicator = wrapper.querySelector('.fk-loading-indicator');

        if (!indicator) {
            indicator = document.createElement('span');
            indicator.className = 'fk-loading-indicator ms-2';
            indicator.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Buscando...';
            wrapper.appendChild(indicator);
        }

        indicator.style.display = 'inline-block';
    }

    /**
     * Esconde indicador de carregamento
     */
    function hideLoadingIndicator(field) {
        const wrapper = field.closest('.form-group') || field.parentElement;
        const indicator = wrapper.querySelector('.fk-loading-indicator');

        if (indicator) {
            indicator.style.display = 'none';
        }
    }

    /**
     * Exibe mensagem de erro
     */
    function showErrorMessage(message) {
        // Usa toast do Bootstrap se disponível
        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            const toast = document.createElement('div');
            toast.className = 'toast align-items-center text-white bg-danger border-0';
            toast.setAttribute('role', 'alert');
            toast.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">${message}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            `;

            document.body.appendChild(toast);
            const bsToast = new bootstrap.Toast(toast);
            bsToast.show();

            toast.addEventListener('hidden.bs.toast', () => toast.remove());
        } else {
            // Fallback para alert
            alert(message);
        }
    }

    // Inicializa quando o script é carregado
    initFKRelatedFields();

    // Expõe funções globalmente para uso manual
    window.FKRelatedFields = {
        init: initFKRelatedFields,
        refresh: refreshFKField,
        openCRUD: openCRUDModal
    };

})();