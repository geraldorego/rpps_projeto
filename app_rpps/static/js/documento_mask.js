// Função para formatar CPF/CNPJ
function formatarDocumento(valor) {
    // Remove tudo que não é número
    valor = valor.replace(/\D/g, '');
    
    // Formata como CPF se tiver 11 dígitos
    if (valor.length === 11) {
        return valor.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
    }
    // Formata como CNPJ se tiver 14 dígitos
    else if (valor.length === 14) {
        return valor.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5');
    }
    // Se não tiver o número correto de dígitos, retorna como está
    return valor;
}

// Adiciona o event listener para campos de CPF/CNPJ
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('input[data-mask-cpfcnpj="true"]').forEach(input => {
        // Guarda o último valor válido
        let lastValidValue = '';
        
        input.addEventListener('input', function(e) {
            // Remove tudo que não é número
            let valor = this.value.replace(/\D/g, '');
            
            // Se tiver mais que 14 dígitos, corta o excesso
            if (valor.length > 14) {
                valor = valor.slice(0, 14);
            }
            
            // Formata o valor
            const formatado = formatarDocumento(valor);
            
            // Se o valor formatado é diferente do atual, atualiza
            if (formatado !== this.value) {
                this.value = formatado;
                lastValidValue = formatado;
            }
        });

        // No blur, garante que está no formato correto
        input.addEventListener('blur', function() {
            const valor = this.value.replace(/\D/g, '');
            if (valor.length !== 11 && valor.length !== 14) {
                // Se o tamanho está errado, limpa o campo
                this.value = '';
            } else {
                this.value = formatarDocumento(valor);
            }
        });
    });
});