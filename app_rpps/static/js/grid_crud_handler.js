// ===============================================
// grid_crud_handler.js
// Autor: Sistema RPPS - Gerado automaticamente
// Versão: 2025.11.19
// Objetivo: Gerenciar CRUD, filtros e ordenação na grid de pesquisa
// ===============================================

(function() {
    'use strict';

    console.log('%c[GRID_CRUD] Módulo carregado', 'color: green; font-weight: bold;');

    // ========== HELPERS ==========
    
    // Exibe mensagens na área #mensagens
    function showMessage(type, text, timeout = 5000) {
        const container = document.getElementById('mensagens');
        if (!container) {
            console.warn('[GRID_CRUD] Container #mensagens não encontrado');
            return;
        }
        
        const iconMap = {
            success: 'check-circle-fill',
            danger: 'exclamation-triangle-fill',
            warning: 'exclamation-circle-fill',
            info: 'info-circle-fill'
        };
        
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show py-2 mb-1`;
        alert.setAttribute('role', 'alert');
        alert.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-${iconMap[type] || 'info-circle-fill'} me-2"></i>
                <div>${text}</div>
            </div>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Fechar"></button>
        `;
        
        container.appendChild(alert);
        
        if (timeout) {
            setTimeout(() => {
                if (alert.parentNode) {
                    const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                    bsAlert.close();
                }
            }, timeout);
        }
    }

    // Retorna o modal de topo (último aberto)
    function getTopModal() {
        const modals = Array.from(document.querySelectorAll('.modal.show'));
        return modals.length ? modals[modals.length - 1] : null;
    }

    // ========== RECARREGAR GRID ==========
    
    async function reloadGrid(extraParams = {}) {
        const gridContainer = document.getElementById('search-grid-container');
        if (!gridContainer) {
            console.warn('[GRID_CRUD] Container #search-grid-container não encontrado');
            return;
        }

        // Pega tabela do contexto (assume que está no botão de pesquisa ou no form)
        const btnNovo = document.getElementById('btn-novo-registro');
        const tabela = btnNovo ? btnNovo.getAttribute('data-tabela') : '';
        
        if (!tabela) {
            console.error('[GRID_CRUD] Tabela não identificada para reload');
            return;
        }

        // Coleta parâmetros atuais (filtro, ordenação, página)
        const filterInput = document.getElementById('grid-filter-input');
        const params = new URLSearchParams();
        
        if (filterInput && filterInput.value.trim()) {
            params.append('search', filterInput.value.trim());
        }

        // Adiciona parâmetros extras (sort_field, sort_dir, etc)
        Object.keys(extraParams).forEach(key => {
            params.append(key, extraParams[key]);
        });

        const url = `/modal-search/${tabela}/?${params.toString()}`;
        
        try {
            const resp = await fetch(url, {
                headers: { 'HX-Request': 'true' },
                credentials: 'same-origin'
            });
            
            if (!resp.ok) throw new Error(`Erro ${resp.status}`);
            
            const html = await resp.text();
            
            // Extrai apenas o conteúdo da grid (partial)
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const newGrid = doc.querySelector('#search-grid-container');
            
            if (newGrid) {
                gridContainer.innerHTML = newGrid.innerHTML;
                console.log('[GRID_CRUD] Grid recarregada com sucesso');
                
                // Re-processa HTMX se existir
                if (typeof htmx !== 'undefined') {
                    htmx.process(gridContainer);
                }
                
                // Re-inicializa radio checkboxes
                if (typeof initRadioCheckboxBehavior === 'function') {
                    initRadioCheckboxBehavior();
                }
            } else {
                console.warn('[GRID_CRUD] Nova grid não encontrada no HTML retornado');
            }
            
        } catch (err) {
            console.error('[GRID_CRUD] Erro ao recarregar grid:', err);
            showMessage('danger', 'Falha ao atualizar a grid.');
        }
    }

    // ========== MODAL CRUD (Novo/Editar) ==========
    
    async function openCrudModal(tabela, recordId = null) {
        const modalEl = document.getElementById('modal-crud');
        if (!modalEl) {
            console.error('[GRID_CRUD] Modal #modal-crud não encontrado');
            return;
        }

        const modalTitle = document.getElementById('modal-crud-title');
        const modalBody = document.getElementById('modal-crud-body');
        
        if (modalTitle) {
            modalTitle.textContent = recordId ? 'Editar Registro' : 'Novo Registro';
        }

        // Mostra loading
        if (modalBody) {
            modalBody.innerHTML = `
                <div class="text-center py-4">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Carregando...</span>
                    </div>
                </div>
            `;
        }

        const modal = new bootstrap.Modal(modalEl);
        modal.show();

        // Monta URL com modal=simple para retornar apenas o formulário simples
        // Nota: o parâmetro sempre se chama 'id' na URL, mas o backend resolve para a PK correta
        const url = recordId 
            ? `/${tabela}/?id=${encodeURIComponent(recordId)}&modal=simple`
            : `/${tabela}/?modal=simple`;

        try {
            const resp = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            });

            if (!resp.ok) throw new Error(`Erro ${resp.status}`);

            const html = await resp.text();
            
            if (modalBody) {
                modalBody.innerHTML = html;
                console.log('[GRID_CRUD] Formulário carregado no modal');
                
                // Re-processa HTMX se necessário
                if (typeof htmx !== 'undefined') {
                    htmx.process(modalBody);
                }
            }

        } catch (err) {
            console.error('[GRID_CRUD] Erro ao abrir modal CRUD:', err);
            if (modalBody) {
                modalBody.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle"></i>
                        Erro ao carregar formulário: ${err.message}
                    </div>
                `;
            }
        }
    }

    // ========== SALVAR FORMULÁRIO ==========
    
    async function submitCrudForm() {
        const modalBody = document.getElementById('modal-crud-body');
        const form = modalBody ? modalBody.querySelector('form#dynamic-form') : null;
        
        if (!form) {
            showMessage('warning', 'Formulário não encontrado no modal.');
            return;
        }

        const action = form.action || window.location.pathname;
        const method = (form.method || 'post').toUpperCase();
        const data = new FormData(form);

        // Força acao=salvar se não estiver definido
        if (!data.has('acao')) {
            data.append('acao', 'salvar');
        }

        try {
            const resp = await fetch(action, {
                method,
                body: data,
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            });

            const contentType = resp.headers.get('Content-Type') || '';
            
            // Se retornar JSON (resposta de sucesso)
            if (contentType.includes('application/json')) {
                const json = await resp.json();
                
                if (json.success) {
                    showMessage('success', json.message || 'Registro salvo com sucesso!');
                    
                    // Fecha modal
                    const modalEl = document.getElementById('modal-crud');
                    if (modalEl) {
                        const modal = bootstrap.Modal.getInstance(modalEl);
                        if (modal) modal.hide();
                    }
                    
                    // Recarrega grid
                    await reloadGrid();
                    
                } else {
                    showMessage('warning', json.message || 'Não foi possível salvar o registro.');
                }
                
                return;
            }

            // Se retornar HTML (formulário com erros de validação)
            const html = await resp.text();
            
            if (modalBody) {
                modalBody.innerHTML = html;
                console.log('[GRID_CRUD] Formulário recarregado com erros de validação');
                
                // Re-processa HTMX
                if (typeof htmx !== 'undefined') {
                    htmx.process(modalBody);
                }
            }

        } catch (err) {
            console.error('[GRID_CRUD] Erro ao salvar:', err);
            showMessage('danger', 'Erro ao salvar registro.');
        }
    }

    // ========== EXCLUIR COM CONFIRMAÇÃO ==========
    
    async function confirmDelete(tabela, recordId) {
        if (!confirm('⚠️ Confirma exclusão deste registro?\n\nEsta operação não pode ser desfeita.\n\nSe houver registros relacionados, a exclusão será bloqueada.')) {
            return;
        }

        try {
            const fd = new FormData();
            fd.append('acao', 'excluir');
            fd.append('csrfmiddlewaretoken', getCsrfToken());

            // URL precisa incluir o record_id: /tratamento/{tabela}/{id}/
            const resp = await fetch(`/tratamento/${tabela}/${recordId}/`, {
                method: 'POST',
                body: fd,
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            });

            const contentType = resp.headers.get('Content-Type') || '';
            
            if (contentType.includes('application/json')) {
                const json = await resp.json();
                
                if (json.success) {
                    showMessage('success', json.message || 'Registro excluído com sucesso!');
                    await reloadGrid();
                } else {
                    showMessage('warning', json.message || 'Não foi possível excluir (pode haver registros relacionados).');
                }
            } else {
                // Backend não retornou JSON
                showMessage('warning', 'Exclusão não confirmada pelo servidor.');
            }

        } catch (err) {
            console.error('[GRID_CRUD] Erro ao excluir:', err);
            showMessage('danger', 'Erro ao excluir registro.');
        }
    }

    // Helper para obter CSRF token
    function getCsrfToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }

    // ========== EVENT DELEGATION (grid buttons) ==========
    
    document.addEventListener('click', function(e) {
        // Botão EDITAR
        const editBtn = e.target.closest('.btn-edit');
        if (editBtn) {
            const row = editBtn.closest('tr[data-record-id]');
            if (row) {
                const tabela = row.getAttribute('data-tabela');
                const id = row.getAttribute('data-record-id');
                console.log(`[GRID_CRUD] Editar: ${tabela} / ${id}`);
                openCrudModal(tabela, id);
            }
            return;
        }

        // Botão EXCLUIR
        const deleteBtn = e.target.closest('.btn-delete');
        if (deleteBtn) {
            const row = deleteBtn.closest('tr[data-record-id]');
            if (row) {
                const tabela = row.getAttribute('data-tabela');
                const id = row.getAttribute('data-record-id');
                console.log(`[GRID_CRUD] Excluir: ${tabela} / ${id}`);
                confirmDelete(tabela, id);
            }
            return;
        }

        // Botão NOVO (na barra do modal de pesquisa)
        const novoBtn = e.target.closest('#btn-novo-registro');
        if (novoBtn) {
            const tabela = novoBtn.getAttribute('data-tabela');
            console.log(`[GRID_CRUD] Novo: ${tabela}`);
            openCrudModal(tabela, null);
            return;
        }

        // Botão SALVAR do modal CRUD
        const salvarBtn = e.target.closest('#modal-crud-salvar');
        if (salvarBtn) {
            console.log('[GRID_CRUD] Submit do formulário modal');
            submitCrudForm();
            return;
        }
    });

    // ========== FILTRO GENÉRICO ==========
    
    const filterInput = document.getElementById('grid-filter-input');
    const filterBtn = document.getElementById('grid-filter-btn');
    
    if (filterBtn && filterInput) {
        filterBtn.addEventListener('click', function() {
            const query = filterInput.value.trim();
            console.log(`[GRID_CRUD] Filtrar: "${query}"`);
            reloadGrid({ search: query });
        });

        // Enter no campo de filtro
        filterInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                filterBtn.click();
            }
        });
    }

    // ========== ORDENAÇÃO POR COLUNA ==========
    
    document.addEventListener('click', function(e) {
        const th = e.target.closest('th.sortable');
        if (!th) return;

        const field = th.getAttribute('data-field');
        const currentDir = th.getAttribute('data-sort-dir') || 'none';
        const newDir = currentDir === 'asc' ? 'desc' : 'asc';

        console.log(`[GRID_CRUD] Ordenar: ${field} ${newDir}`);

        // Atualiza visual
        document.querySelectorAll('th.sortable').forEach(h => {
            h.setAttribute('data-sort-dir', 'none');
            h.setAttribute('aria-sort', 'none');
            const icon = h.querySelector('.sort-icon');
            if (icon) icon.className = 'bi bi-chevron-expand ms-1 sort-icon';
        });

        th.setAttribute('data-sort-dir', newDir);
        th.setAttribute('aria-sort', newDir === 'asc' ? 'ascending' : 'descending');
        
        const icon = th.querySelector('.sort-icon');
        if (icon) {
            icon.className = newDir === 'asc' 
                ? 'bi bi-chevron-up ms-1 sort-icon'
                : 'bi bi-chevron-down ms-1 sort-icon';
        }

        // Atualiza indicador
        const indicator = document.getElementById('grid-sort-indicator');
        if (indicator) {
            indicator.textContent = `Ordenado por ${field} (${newDir === 'asc' ? 'A→Z' : 'Z→A'})`;
        }

        // Recarrega com ordenação
        const query = filterInput ? filterInput.value.trim() : '';
        reloadGrid({ 
            search: query, 
            sort_field: field, 
            sort_dir: newDir 
        });
    });

    // ========== INICIALIZAÇÃO ==========
    
    console.log('[GRID_CRUD] Handlers de evento configurados');

})();
