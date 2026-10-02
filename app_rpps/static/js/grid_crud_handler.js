// ===============================================
// grid_crud_handler.js
// Autor: Sistema RPPS - Gerado automaticamente
// Versão: 2025.11.19
// Objetivo: Gerenciar CRUD, filtros e ordenação na grid de pesquisa
// ===============================================

(function() {
    'use strict';

    if (window.gridCrudHandlerInitialized) return;
    window.gridCrudHandlerInitialized = true;

    console.log('%c[GRID_CRUD] Módulo carregado', 'color: green; font-weight: bold;');

    let activeSortField = null;
    let activeSortDirection = 'none';

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

    function getGridFilterInput() {
        return document.getElementById('grid-filter-input');
    }

    function updateSortIndicators(root = document) {
        root.querySelectorAll('th.sortable').forEach(function(header) {
            const isActive = header.dataset.field === activeSortField;
            const direction = isActive ? activeSortDirection : 'none';
            header.dataset.sortDir = direction;
            header.setAttribute('aria-sort', direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none');
            const icon = header.querySelector('.sort-icon');
            if (icon) {
                icon.className = direction === 'asc' ?
                    'bi bi-chevron-up ms-1 sort-icon' :
                    direction === 'desc' ? 'bi bi-chevron-down ms-1 sort-icon' :
                    'bi bi-chevron-expand ms-1 sort-icon';
            }
        });
    }

    function filterLoadedGrid(query) {
        const gridContainer = document.getElementById('search-grid-container');
        const table = gridContainer && gridContainer.querySelector('table');
        const body = table && table.tBodies[0];
        if (!body) return false;

        const normalizedQuery = String(query || '').trim().toLocaleLowerCase();
        const headers = Array.from(table.querySelectorAll('thead th.sortable'));
        const sortedColumn = activeSortField ? headers.findIndex(header => header.dataset.field === activeSortField) : -1;
        const rows = Array.from(body.querySelectorAll('tr[data-record-id]'));

        rows.forEach(function(row) {
            const cells = Array.from(row.cells).slice(1, -1);
            const searchableCells = sortedColumn >= 0 ? [cells[sortedColumn]] : cells;
            const matches = !normalizedQuery || searchableCells.some(function(cell) {
                return cell && cell.textContent.toLocaleLowerCase().includes(normalizedQuery);
            });
            row.hidden = !matches;
        });
        return true;
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
        const filterInput = getGridFilterInput();
        const params = new URLSearchParams();

        if (filterInput && filterInput.value.trim()) {
            params.append('search', filterInput.value.trim());
        }

        // Adiciona parâmetros extras (sort_field, sort_dir, etc)
        Object.keys(extraParams).forEach(key => {
            params.append(key, extraParams[key]);
        });
        if (activeSortField && !Object.prototype.hasOwnProperty.call(extraParams, 'sort_field')) {
            params.append('sort_field', activeSortField);
            params.append('sort_dir', activeSortDirection);
        }

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
                if (Object.prototype.hasOwnProperty.call(extraParams, 'sort_field')) {
                    activeSortField = extraParams.sort_field;
                    activeSortDirection = extraParams.sort_dir || 'desc';
                }
                updateSortIndicators(gridContainer);
                filterLoadedGrid(filterInput ? filterInput.value : '');
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

    async function openCrudModal(tabela, recordId = null, fkContext = null) {
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
        const url = recordId ?
            `/${tabela}/?id=${encodeURIComponent(recordId)}&modal=simple` :
            `/${tabela}/?modal=simple`;

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
                const form = modalBody.querySelector('form#dynamic-form');
                if (form) {
                    form.dataset.tabela = tabela;
                    if (fkContext && fkContext.isFkSearch === 'true') {
                        form.dataset.parentTable = fkContext.parentTable;
                        form.dataset.fkFieldName = fkContext.fkFieldName;
                    }
                }

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
        if (form.dataset.parentTable && form.dataset.fkFieldName) {
            data.append('parent_table', form.dataset.parentTable);
            data.append('fk_field_name', form.dataset.fkFieldName);
        }

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

                    if (json.reference) {
                        const parentForm = Array.from(document.querySelectorAll('form#dynamic-form'))
                            .find(candidate => candidate !== form && candidate.dataset.tabela === form.dataset.parentTable);
                        const parentField = parentForm && parentForm.querySelector('[name="' + json.reference.field + '"]');
                        if (parentField) {
                            const key = String(json.reference.key);
                            if (parentField.tagName === 'SELECT' && !Array.from(parentField.options).some(option => option.value === key)) {
                                parentField.add(new Option(json.reference.display || key, key));
                            }
                            parentField.value = key;
                            parentField.dispatchEvent(new Event('input', { bubbles: true }));
                            parentField.dispatchEvent(new Event('change', { bubbles: true }));
                            const display = parentForm.querySelector('[data-fk-display-for="' + json.reference.field + '"]');
                            if (display) display.textContent = json.reference.display || '';
                        }
                    }

                    // Fecha modal
                    const modalEl = document.getElementById('modal-crud');
                    if (modalEl) {
                        const modal = bootstrap.Modal.getInstance(modalEl);
                        if (modal) modal.hide();
                    }

                    // Recarrega grid
                    await reloadGrid();
                    if (json.reference) {
                        const searchModal = document.getElementById('modal');
                        const searchModalInstance = searchModal && bootstrap.Modal.getInstance(searchModal);
                        if (searchModalInstance) searchModalInstance.hide();
                    }

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

    async function submitPeriodCopy(phase) {
        const modal = document.getElementById('copy-period-modal');
        const trigger = document.querySelector('[data-copy-period-trigger]');
        const summary = document.getElementById('copy-period-summary');
        const confirmButton = document.getElementById('copy-period-confirm');
        if (!modal || !trigger || !summary) return;

        const periodInputs = Array.from(modal.querySelectorAll('[data-copy-period]'));
        const missingInput = periodInputs.find(input => input.required && !input.value.trim());
        if (missingInput) {
            missingInput.focus();
            summary.textContent = 'Preencha os períodos de origem e destino antes de continuar.';
            if (confirmButton) confirmButton.disabled = true;
            return;
        }

        const payload = new URLSearchParams();
        payload.append('fase', phase);
        if (phase === 'execute') payload.append('confirmado', 'true');
        periodInputs.forEach(function(input) {
            payload.append(input.dataset.copyPeriod + '_' + input.dataset.copyField, input.value);
        });
        const csrfInput = document.querySelector('#dynamic-form [name="csrfmiddlewaretoken"]');
        if (csrfInput) payload.append('csrfmiddlewaretoken', csrfInput.value);

        const actionButton = phase === 'preview' ? document.getElementById('copy-period-preview') : confirmButton;
        if (actionButton) actionButton.disabled = true;
        summary.textContent = phase === 'preview' ? 'Consultando registros de origem…' : 'Copiando registros…';

        try {
            const response = await fetch(trigger.dataset.copyUrl, {
                method: 'POST',
                body: payload,
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            });
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || 'Falha ao copiar registros.');

            if (phase === 'preview') {
                summary.textContent = `Foram encontrados ${result.encontrados} registro(s) no período de origem. Confirme para gravar no destino.`;
                if (confirmButton) {
                    confirmButton.hidden = result.encontrados === 0;
                    confirmButton.disabled = result.encontrados === 0;
                }
                return;
            }

            summary.textContent = `Cópia concluída: ${result.copied} copiado(s), ${result.ignored} ignorado(s) por já existir e ${result.errors} erro(s).`;
            if (confirmButton) confirmButton.hidden = true;
        } catch (error) {
            summary.textContent = error.message;
        } finally {
            if (actionButton && phase === 'preview') actionButton.disabled = false;
            if (confirmButton && phase === 'execute') confirmButton.disabled = false;
        }
    }

    // Helper para obter CSRF token
    function getCsrfToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }

    // ========== EVENT DELEGATION (grid buttons) ==========

    document.addEventListener('click', function(e) {
        const copyTrigger = e.target.closest('[data-copy-period-trigger]');
        if (copyTrigger) {
            const modalElement = document.getElementById('copy-period-modal');
            if (!modalElement) return;
            const parentForm = document.getElementById('dynamic-form');
            const summary = document.getElementById('copy-period-summary');
            const confirmButton = document.getElementById('copy-period-confirm');
            modalElement.querySelectorAll('[data-copy-period="origem"]').forEach(function(input) {
                const currentField = parentForm && parentForm.elements.namedItem(input.dataset.copyField);
                input.value = currentField && currentField.value ? currentField.value : '';
            });
            modalElement.querySelectorAll('[data-copy-period="destino"]').forEach(function(input) {
                input.value = '';
            });
            if (summary) summary.textContent = '';
            if (confirmButton) {
                confirmButton.hidden = true;
                confirmButton.disabled = true;
            }
            bootstrap.Modal.getOrCreateInstance(modalElement).show();
            return;
        }

        if (e.target.closest('#copy-period-preview')) {
            submitPeriodCopy('preview');
            return;
        }

        if (e.target.closest('#copy-period-confirm')) {
            submitPeriodCopy('execute');
            return;
        }

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
            openCrudModal(tabela, null, {
                parentTable: novoBtn.dataset.parentTable,
                fkFieldName: novoBtn.dataset.fkFieldName,
                isFkSearch: novoBtn.dataset.isFkSearch
            });
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

    document.addEventListener('input', function(event) {
        if (!event.target || !event.target.matches('#copy-period-modal [data-copy-period]')) return;
        const periodSize = parseInt(event.target.dataset.copySize, 10);
        if (event.target.dataset.copyDigits === 'true') {
            let digits = event.target.value.replace(/\D/g, '');
            if (periodSize) digits = digits.slice(0, periodSize);
            if (digits !== event.target.value) event.target.value = digits;
        }
        const summary = document.getElementById('copy-period-summary');
        const confirmButton = document.getElementById('copy-period-confirm');
        if (summary) summary.textContent = 'Os períodos foram alterados. Pré-visualize novamente antes de confirmar.';
        if (confirmButton) {
            confirmButton.hidden = true;
            confirmButton.disabled = true;
        }
    });

    // ========== FILTRO GENÉRICO ==========

    document.addEventListener('input', function(event) {
        if (!event.target || event.target.id !== 'grid-filter-input') return;
        filterLoadedGrid(event.target.value);
    });

    document.addEventListener('keydown', function(event) {
        if (!event.target || event.target.id !== 'grid-filter-input' || event.key !== 'Enter') return;
        event.preventDefault();
        if (!filterLoadedGrid(event.target.value)) {
            reloadGrid({ search: event.target.value.trim() });
        }
    });

    document.addEventListener('click', function(event) {
        const filterButton = event.target.closest('#grid-filter-btn');
        if (!filterButton) return;
        const filterInput = getGridFilterInput();
        const query = filterInput ? filterInput.value.trim() : '';
        if (!filterLoadedGrid(query)) {
            reloadGrid({ search: query });
        }
    });

    document.body.addEventListener('htmx:afterSwap', function(event) {
        const target = event.detail && event.detail.target;
        if (!target) return;

        if (target.id === 'modal') {
            activeSortField = null;
            activeSortDirection = 'none';
            const gridContainer = target.querySelector('#search-grid-container');
            const filterInput = getGridFilterInput();
            updateSortIndicators(gridContainer || target);
            if (gridContainer) filterLoadedGrid(filterInput ? filterInput.value : '');
            return;
        }

        if (target.id === 'search-grid-container') {
            const filterInput = getGridFilterInput();
            updateSortIndicators(target);
            filterLoadedGrid(filterInput ? filterInput.value : '');
        }
    });

    // ========== ORDENAÇÃO POR COLUNA ==========

    document.addEventListener('click', function(e) {
        const th = e.target.closest('th.sortable');
        if (!th) return;

        const field = th.getAttribute('data-field');
        const currentDir = activeSortField === field ? activeSortDirection : 'none';
        const newDir = currentDir === 'asc' ? 'desc' : 'asc';

        console.log(`[GRID_CRUD] Ordenar: ${field} ${newDir}`);

        activeSortField = field;
        activeSortDirection = newDir;
        updateSortIndicators();

        // Atualiza indicador
        const indicator = document.getElementById('grid-sort-indicator');
        if (indicator) {
            indicator.textContent = `Ordenado por ${field} (${newDir === 'asc' ? 'A→Z' : 'Z→A'})`;
        }

        // Recarrega com ordenação
        const filterInput = getGridFilterInput();
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