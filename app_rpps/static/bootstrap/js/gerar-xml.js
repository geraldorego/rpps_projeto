document.addEventListener('DOMContentLoaded', function() {
    const gerarXmlBtn = document.querySelector('[data-bs-target="#xmlModal"]');
    
    if (gerarXmlBtn) {
        gerarXmlBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Inicializa a modal corretamente
            const xmlModal = new bootstrap.Modal(document.getElementById('xmlModal'), {
                backdrop: 'static',
                keyboard: false
            });
            
            xmlModal.show();
            
            // Submete o formulário via AJAX
            const form = document.getElementById('dynamic-form');
            const formData = new FormData(form);
            formData.append('acao', 'gerar_xml');
            
            fetch(form.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Erro na rede');
                }
                return response.json();
            })
            .then(data => {
                const modalContent = document.getElementById('xmlModalContent');
                
                if (data.status === 'success') {
                    let html = `
                        <div class="table-responsive">
                            <table class="table table-striped table-hover">
                                <thead class="table-light">
                                    <tr>
                                        <th>Arquivo</th>
                                        <th>Status</th>
                                        <th>Detalhes</th>
                                        <th>Ação</th>
                                    </tr>
                                </thead>
                                <tbody>`;
                    
                    let hasDownloads = false;
                    
                    data.xml_data.forEach(item => {
                        const isSuccess = item.xml_gerado;
                        hasDownloads = hasDownloads || isSuccess;
                        
                        html += `
                            <tr>
                                <td>${item.nomarq}</td>
                                <td>
                                    <span class="badge ${isSuccess ? 'bg-success' : 'bg-danger'}">
                                        ${isSuccess ? 'Sucesso' : 'Falha'}
                                    </span>
                                </td>
                                <td>
                                    ${isSuccess ? 
                                        'XML gerado com sucesso' : 
                                        (item.motivo_vazio || item.motivo_geracao || 'Erro desconhecido')}
                                </td>
                                <td>
                                    ${isSuccess ? 
                                        `<a href="${item.xml_link}" class="btn btn-sm btn-outline-primary" download>
                                            <i class="bi bi-download"></i> Baixar
                                        </a>` : 
                                        '-'}
                                </td>
                            </tr>`;
                    });
                    
                    html += `</tbody></table></div>`;
                    modalContent.innerHTML = html;
                    
                    // Mostra o botão de baixar todos se houver arquivos
                    if (hasDownloads) {
                        document.getElementById('btnDownloadAll').style.display = 'inline-block';
                        document.getElementById('btnDownloadAll').onclick = function() {
                            data.xml_data.filter(item => item.xml_gerado).forEach(item => {
                                const link = document.createElement('a');
                                link.href = item.xml_link;
                                link.download = `${item.nomarq}.xml`;
                                document.body.appendChild(link);
                                link.click();
                                document.body.removeChild(link);
                            });
                        };
                    }
                } else {
                    modalContent.innerHTML = `
                        <div class="alert alert-danger">
                            <i class="bi bi-exclamation-triangle-fill"></i>
                            ${data.message || 'Erro ao gerar XMLs'}
                        </div>`;
                }
            })
            .catch(error => {
                document.getElementById('xmlModalContent').innerHTML = `
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle-fill"></i>
                        Erro na requisição: ${error.message}
                    </div>`;
            });
        });
    }
});