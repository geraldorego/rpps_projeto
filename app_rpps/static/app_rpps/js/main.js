(function() {
    'use strict';

    const isFormSwapTarget = function(target) {
        return target && (target.id === 'dynamic-form' || target.id === 'form-container');
    };

    const AppRpps = {
        initialized: false,
        fieldBlurInitialized: false,
        foreignKeyInitialized: false,
        formInitialized: false,

        init: function() {
            if (this.initialized) return;

            this.initFieldBlur();
            this.initForeignKeyHandlers();
            this.initFormHandlers();

            this.initialized = true;
        },

        initFieldBlur: function() {
            if (this.fieldBlurInitialized) return;
            this.fieldBlurInitialized = true;

            const bindBlurCheck = function() {
                const form = document.getElementById('dynamic-form');
                if (!form) return;

                form.querySelectorAll('[data-campo-blur="true"]').forEach(function(campo) {
                    if (campo.dataset.appRppsBlurBound === 'true') return;
                    campo.dataset.appRppsBlurBound = 'true';

                    campo.addEventListener('blur', function() {
                        const checkUrl = this.getAttribute('data-check-url');
                        const camposRelacionados = this.getAttribute('data-campos-relacionados') || '';
                        if (!checkUrl) return;

                        const related = camposRelacionados
                            .split(',')
                            .map(function(item) { return item.trim(); })
                            .filter(Boolean);

                        const requiredKeys = Array.from(new Set([].concat(related, [this.name])));
                        const missing = requiredKeys.filter(function(nome) {
                            const el = form.querySelector('[name="' + nome + '"]');
                            const value = ((el && el.value) || '').trim();
                            return !value || value === '0';
                        });

                        if (missing.length) {
                            return;
                        }

                        const params = new URLSearchParams();
                        const appended = new Set();
                        requiredKeys.forEach(function(nome) {
                            const el = form.querySelector('[name="' + nome + '"]');
                            if (!el) return;
                            const value = (el.value || '').trim();
                            if (!value || value === '0' || appended.has(nome)) return;
                            params.append(nome, value);
                            appended.add(nome);
                        });

                        const fullUrl = checkUrl + '?' + params.toString();
                        fetch(fullUrl, {
                                headers: {
                                    'HX-Request': 'true',
                                    'Accept': 'text/html'
                                }
                            })
                            .then(function(response) { return response.text(); })
                            .then(function(html) {
                                const parser = new DOMParser();
                                const doc = parser.parseFromString(html, 'text/html');
                                const newForm = doc.querySelector('form#dynamic-form');
                                if (newForm) {
                                    const currentForm = document.getElementById('dynamic-form');
                                    if (currentForm) {
                                        currentForm.replaceWith(newForm);
                                        if (window.htmx) htmx.process(newForm);
                                    }
                                }
                            })
                            .catch(function(error) {
                                console.error('[AppRpps][Blur] Falha no blur-check:', error);
                            });
                    });
                });
            };

            bindBlurCheck();

            document.body.addEventListener('htmx:afterSwap', function(evt) {
                const target = evt.detail && evt.detail.target;
                if (isFormSwapTarget(target)) {
                    bindBlurCheck();
                }
            }, { once: false });
        },

        initForeignKeyHandlers: function() {
            if (this.foreignKeyInitialized) return;
            this.foreignKeyInitialized = true;

            const attachFkBlur = function() {
                // Cobre tanto campos com mapeamento (data-fk-field) quanto FK simples (data-tabela-ref)
                const camposFk = document.querySelectorAll('[data-fk-field], [data-tabela-ref]');
                camposFk.forEach(function(campo) {
                    if (campo.dataset.appRppsFkBound === 'true') return;
                    campo.dataset.appRppsFkBound = 'true';

                    campo.addEventListener('blur', function() {
                        const input = this;
                        const valor = (input.value || '').trim();
                        const fieldName = input.getAttribute('data-fk-field') || input.name;
                        const searchField = input.getAttribute('data-fk-search-field') || fieldName;

                        if (!valor || !fieldName) return;

                        // Evita disparos concorrentes do mesmo campo
                        if (input.dataset.blurring === 'true') return;
                        input.dataset.blurring = 'true';

                        const pathParts = window.location.pathname.split('/');
                        const tabela = pathParts[1];
                        if (!tabela) {
                            input.dataset.blurring = 'false';
                            return;
                        }

                        console.log(`[AppRpps][FK] 🔍 Blur em '${tabela}.${fieldName}' = "${valor}" (tabela_referencia="${input.dataset.tabelaRef || ''}")`);

                        const url = '/' + tabela + '/check-fk/' + encodeURIComponent(fieldName) + '/?' + encodeURIComponent(searchField) + '=' + encodeURIComponent(valor);

                        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                            .then(function(response) { return response.json(); })
                            .then(function(data) {
                                const displayElement = Array.from(document.querySelectorAll('[data-fk-display-for]'))
                                    .find(function(element) { return element.dataset.fkDisplayFor === fieldName; });
                                if (data && data.found && data.data) {
                                    Object.entries(data.data).forEach(function([campoLocal, valorRef]) {
                                        const inputLocal = document.querySelector('[name="' + campoLocal + '"]');
                                        if (inputLocal) {
                                            inputLocal.value = valorRef || '';
                                            inputLocal.dispatchEvent(new Event('change', { bubbles: true }));
                                        }
                                    });
                                    if (displayElement) displayElement.textContent = data.display || '';
                                    const wrapper = input.closest('.col-md-4, .col-md-6, .form-group') || input.parentElement;
                                    Array.from(wrapper.querySelectorAll('[data-fk-create-for]'))
                                        .filter(function(element) { return element.dataset.fkCreateFor === fieldName; })
                                        .forEach(function(element) { element.remove(); });
                                    input.dataset.referenceKey = data.key || '';
                                    input.classList.remove('is-invalid');
                                    input.classList.add('is-valid');
                                } else {
                                    if (displayElement) {
                                        displayElement.textContent = (data && data.can_create) ?
                                            'Registro não encontrado. Use Pesquisar e Novo para cadastrar.' :
                                            (data && data.message) || 'Não foi possível localizar a referência.';
                                    }
                                    if (data && data.can_create) {
                                        const wrapper = input.closest('.col-md-4, .col-md-6, .form-group') || input.parentElement;
                                        let createButton = Array.from(wrapper.querySelectorAll('[data-fk-create-for]'))
                                            .find(function(element) { return element.dataset.fkCreateFor === fieldName; });
                                        if (!createButton) {
                                            createButton = document.createElement('button');
                                            createButton.type = 'button';
                                            createButton.className = 'btn btn-link btn-sm px-0';
                                            createButton.dataset.fkCreateFor = fieldName;
                                            createButton.textContent = 'Cadastrar referência';
                                            createButton.addEventListener('click', function() {
                                                const parentForm = input.closest('form');
                                                const parentTable = parentForm && parentForm.dataset.tabela;
                                                const referenceTable = input.dataset.tabelaRef;
                                                if (!parentTable || !referenceTable || !window.htmx) return;
                                                const params = new URLSearchParams({
                                                    fk_search: 'true',
                                                    parent_table: parentTable,
                                                    fk_field_name: fieldName
                                                });
                                                htmx.ajax('GET', '/modal-search/' + encodeURIComponent(referenceTable) + '/?' + params.toString(), {
                                                    target: '#modal',
                                                    swap: 'innerHTML'
                                                });
                                            });
                                            wrapper.appendChild(createButton);
                                        }
                                    }
                                    input.classList.remove('is-valid');
                                    input.classList.add('is-invalid');
                                }
                            })
                            .catch(function(error) {
                                console.error('[AppRpps][FK] Erro ao buscar dados:', error);
                            })
                            .finally(function() {
                                input.dataset.blurring = 'false';
                            });
                    });
                });
            };

            const attachRelatedFieldListeners = function() {
                const fkFields = document.querySelectorAll('[data-fk-field]');
                fkFields.forEach(function(field) {
                    if (field.dataset.appRppsRelatedBound === 'true') return;
                    field.dataset.appRppsRelatedBound = 'true';

                    const fieldName = field.getAttribute('data-fk-field');
                    const fieldMapping = field.getAttribute('data-field-mapping');

                    if (field.tagName === 'SELECT') {
                        field.addEventListener('change', function() {
                            const fkValue = String(this.value || '');
                            if (!fkValue || !fieldMapping) return;

                            let requestedValues = [];
                            try {
                                requestedValues = JSON.parse(this.dataset.appRppsRelatedRequestedValues || '[]');
                            } catch (error) {
                                requestedValues = [];
                            }
                            if (requestedValues.includes(fkValue)) return;
                            requestedValues.push(fkValue);
                            this.dataset.appRppsRelatedRequestedValues = JSON.stringify(requestedValues);

                            const tabelaElement = document.querySelector('[data-tabela]');
                            const tabela = tabelaElement ? tabelaElement.getAttribute('data-tabela') : null;
                            if (!tabela) return;

                            const url = '/api/related-fields/' + tabela + '/' + fieldName + '/?fk_id=' + encodeURIComponent(this.value);
                            fetch(url)
                                .then(function(response) { return response.json(); })
                                .then(function(data) {
                                    if (String(field.value || '') !== fkValue) return;
                                    if (!data || !data.success || !data.data) return;
                                    Object.entries(data.data).forEach(function([localField, value]) {
                                        const target = document.querySelector('[name="' + localField + '"]') || document.getElementById('id_' + localField);
                                        if (target && target !== field) {
                                            const nextValue = value == null ? '' : String(value);
                                            if (String(target.value || '') === nextValue) return;
                                            target.value = nextValue;
                                            target.dispatchEvent(new Event('change', { bubbles: true }));
                                        }
                                    });
                                })
                                .catch(function(error) {
                                    console.error('[AppRpps][FK] Erro ao carregar campos relacionados:', error);
                                });
                        });
                    }
                });
            };

            const attachDependentSelectHandlers = function() {
                document.querySelectorAll('select[data-fk-deps]').forEach(function(field) {
                    if (field.dataset.appRppsDependenciesBound === 'true') return;
                    field.dataset.appRppsDependenciesBound = 'true';

                    const form = field.closest('form');
                    const fieldName = field.dataset.fkField || field.name;
                    let dependencyMap = {};
                    try {
                        dependencyMap = JSON.parse(field.dataset.fkDeps || '{}');
                    } catch (error) {
                        console.error('[AppRpps][FK] Dependências inválidas:', error);
                        return;
                    }

                    const dependencyNames = Array.from(new Set(Object.values(dependencyMap)));
                    if (!dependencyNames.length) return;

                    const refreshOptions = function() {
                        if (!form || !fieldName) return;

                        const dependencyValues = {};
                        const missing = [];
                        dependencyNames.forEach(function(name) {
                            const dependencyField = form.elements.namedItem(name);
                            const value = dependencyField && typeof dependencyField.value !== 'undefined' ?
                                String(dependencyField.value).trim() :
                                '';
                            if (!value) {
                                missing.push(name);
                            } else {
                                dependencyValues[name] = value;
                            }
                        });

                        const selectedValue = field.value;
                        const requestId = String((Number(field.dataset.optionsRequestId) || 0) + 1);
                        field.dataset.optionsRequestId = requestId;
                        field.replaceChildren(new Option('---------', ''));
                        if (missing.length) {
                            field.value = '';
                            field.dataset.dependenciesReady = 'false';
                            return;
                        }

                        const table = form.dataset.tabela;
                        if (!table) return;

                        const params = new URLSearchParams(dependencyValues);
                        const url = '/api/reference-options/' + encodeURIComponent(table) + '/' +
                            encodeURIComponent(fieldName) + '/?' + params.toString();

                        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                            .then(function(response) {
                                if (!response.ok) throw new Error('HTTP ' + response.status);
                                return response.json();
                            })
                            .then(function(data) {
                                if (field.dataset.optionsRequestId !== requestId) return;
                                field.replaceChildren(new Option('---------', ''));
                                if (!data || !data.ready || !Array.isArray(data.results)) {
                                    field.value = '';
                                    field.dataset.dependenciesReady = 'false';
                                    return;
                                }

                                data.results.forEach(function(option) {
                                    field.add(new Option(option.text, option.value));
                                });
                                field.dataset.dependenciesReady = 'true';
                                field.value = data.results.some(function(option) {
                                    return String(option.value) === selectedValue;
                                }) ? selectedValue : '';
                            })
                            .catch(function(error) {
                                if (field.dataset.optionsRequestId !== requestId) return;
                                field.dataset.dependenciesReady = 'false';
                                console.error('[AppRpps][FK] Erro ao carregar opções dependentes:', error);
                            });
                    };

                    dependencyNames.forEach(function(name) {
                        const dependencyField = form && form.elements.namedItem(name);
                        if (dependencyField && dependencyField !== field) {
                            dependencyField.addEventListener('change', refreshOptions);
                        }
                    });

                    refreshOptions();
                });
            };

            attachFkBlur();
            attachRelatedFieldListeners();
            attachDependentSelectHandlers();

            document.body.addEventListener('htmx:afterSwap', function(evt) {
                const target = evt.detail && evt.detail.target;
                if (isFormSwapTarget(target)) {
                    attachFkBlur();
                    attachRelatedFieldListeners();
                    attachDependentSelectHandlers();
                }
            }, { once: false });
        },

        initFormHandlers: function() {
            if (this.formInitialized) return;
            this.formInitialized = true;

            const applyMasks = function() {
                const formatarDocumento = function(valor) {
                    const digits = (valor || '').replace(/\D/g, '');
                    if (digits.length <= 11) {
                        if (digits.length > 9) return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{1,2})/, '$1.$2.$3-$4');
                        if (digits.length > 6) return digits.replace(/(\d{3})(\d{3})(\d{1,3})/, '$1.$2.$3');
                        if (digits.length > 3) return digits.replace(/(\d{3})(\d{1,3})/, '$1.$2');
                        return digits;
                    }

                    if (digits.length > 14) return digits.slice(0, 14).replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
                    if (digits.length > 12) return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{1,2})/, '$1.$2.$3/$4-$5');
                    if (digits.length > 8) return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{1,4})/, '$1.$2.$3/$4');
                    if (digits.length > 5) return digits.replace(/(\d{2})(\d{3})(\d{1,3})/, '$1.$2.$3');
                    if (digits.length > 2) return digits.replace(/(\d{2})(\d{1,3})/, '$1.$2');
                    return digits;
                };

                document.querySelectorAll('input[data-mask-cpfcnpj="true"]').forEach(function(input) {
                    if (input.dataset.appRppsMaskBound === 'true') return;
                    input.dataset.appRppsMaskBound = 'true';

                    input.addEventListener('input', function() {
                        const current = this.value;
                        const formatted = formatarDocumento(this.value);
                        if (formatted !== current) {
                            this.value = formatted;
                        }
                    });

                    input.addEventListener('blur', function() {
                        const digits = (this.value || '').replace(/\D/g, '');
                        if (digits && digits.length !== 11 && digits.length !== 14) {
                            this.value = '';
                            this.classList.add('is-invalid');
                        }
                    });
                });
            };

            const configureNavigation = function() {
                const form = document.getElementById('dynamic-form');
                if (!form) return;

                const getNextFocusableElement = function(currentElement) {
                    const focusable = Array.from(form.querySelectorAll('input:not([type="hidden"]), select, textarea'))
                        .filter(function(el) {
                            return !el.disabled && !el.readOnly && getComputedStyle(el).display !== 'none';
                        });
                    const currentIndex = focusable.indexOf(currentElement);
                    return focusable[currentIndex + 1] || null;
                };

                form.querySelectorAll('input, select, textarea').forEach(function(input) {
                    if (input.dataset.appRppsNavigationBound === 'true') return;
                    input.dataset.appRppsNavigationBound = 'true';

                    input.addEventListener('keydown', function(event) {
                        if (event.key === 'Enter' && this.tagName.toLowerCase() !== 'textarea') {
                            event.preventDefault();
                            const nextElement = getNextFocusableElement(this);
                            if (nextElement) {
                                nextElement.focus();
                            }
                        }
                    });
                });
            };

            const configureValidation = function() {
                const form = document.getElementById('dynamic-form');
                if (!form || form.dataset.appRppsValidationBound === 'true') return;
                form.dataset.appRppsValidationBound = 'true';

                form.addEventListener('submit', function(event) {
                    const submitButton = document.activeElement;
                    if (submitButton && submitButton.value === 'excluir') return;

                    if (!this.checkValidity()) {
                        event.preventDefault();
                        event.stopPropagation();
                        const firstInvalidField = this.querySelector(':invalid');
                        if (firstInvalidField) {
                            firstInvalidField.focus();
                        }
                    }
                    this.classList.add('was-validated');
                });
            };

            applyMasks();
            configureNavigation();
            configureValidation();

            document.body.addEventListener('htmx:afterSwap', function(evt) {
                const target = evt.detail && evt.detail.target;
                if (isFormSwapTarget(target)) {
                    applyMasks();
                    configureNavigation();
                    configureValidation();
                }
            }, { once: false });
        }
    };

    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.btn-pesquisa');
        if (!btn) return;

        const inputGroup = btn.closest('.input-group');
        const input = inputGroup ? inputGroup.querySelector('input, select') : null;
        const inputId = input ? input.id : 'desconhecido';
        const inputValue = input ? input.value : 'vazio';

        if (input && input.hasAttribute('readonly')) {
            input.setAttribute('tabindex', '-1');
            input.style.cursor = 'not-allowed';
        }

        console.log(`[AppRpps] 🔍 Clique na lupa: ${inputId} (valor atual: "${inputValue}")`);
        console.log(`[AppRpps] 🔍 URL: ${btn.getAttribute('hx-get')}`);
    });

    document.addEventListener('htmx:afterSwap', function(evt) {
        if (!evt.target || evt.target.id !== 'modal') return;

        try {
            const modalEl = document.getElementById('modal');
            if (!modalEl) {
                console.error('[AppRpps] ❌ Elemento #modal não encontrado');
                return;
            }

            const modal = new bootstrap.Modal(modalEl, {
                backdrop: 'static',
                keyboard: true
            });
            modal.show();
            console.log('[AppRpps] ✅ Modal aberta com sucesso');
        } catch (error) {
            console.error('[AppRpps] ❌ Erro ao abrir modal:', error);
        }
    });

    const ensureReadonlySearchButtons = function() {
        document.querySelectorAll('.btn-pesquisa').forEach(function(btn) {
            const inputGroup = btn.closest('.input-group');
            if (!inputGroup) return;

            const input = inputGroup.querySelector('input, select');
            if (!input) return;

            if (input.hasAttribute('readonly')) {
                input.setAttribute('tabindex', '-1');
                input.style.cursor = 'not-allowed';
            }
        });
    };

    ensureReadonlySearchButtons();
    document.body.addEventListener('htmx:afterSwap', function(evt) {
        const target = evt.detail && evt.detail.target;
        if (target && (target.id === 'dynamic-form' || target.id === 'modal')) {
            ensureReadonlySearchButtons();
        }
    }, { once: false });

    document.addEventListener('DOMContentLoaded', function() {
        AppRpps.init();
    });

    window.AppRpps = AppRpps;
})();