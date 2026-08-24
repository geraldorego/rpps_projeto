from django.db import connection

from .metadata_helpers import validate_table_name, validate_columns, validate_column_name


def get_referencia_data(config, filtros=None):
    """Busca dados da tabela de referência com base na configuração"""
    if not config or not config.get('tabela'):
        return []

    tabela = validate_table_name(config['tabela'])
    campos = validate_columns(tabela, config.get('campos_retorno', ['id', 'descricao']))

    with connection.cursor() as cursor:
        where = ""
        params = []

        if filtros:
            where_clauses = []
            for k, v in filtros.items():
                if v is None:
                    continue

                coluna = str(k).strip()
                if not coluna:
                    continue

                coluna_validada = validate_column_name(tabela, coluna)
                where_clauses.append(f"{connection.ops.quote_name(coluna_validada)} = %s")
                params.append(v)

            if where_clauses:
                where = "WHERE " + " AND ".join(where_clauses)

        query = f"SELECT {', '.join(connection.ops.quote_name(c) for c in campos)} FROM {connection.ops.quote_name(tabela)} {where}"
        cursor.execute(query, params)

        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

def format_referencia_html(dados, config):
    """Formata os dados conforme a configuração JSON"""
    tipo = config.get('tipo_display', 'label')
    campos = config.get('campos_retorno', ['id', 'descricao'])
    params = config.get('params', {})
    
    if tipo == 'tabela':
        classes = params.get('css_class', 'table table-sm')
        html = f'<table class="{classes}">'
        
        if params.get('mostrar_cabecalho', True):
            html += '<tr>' + ''.join(f'<th>{c}</th>' for c in campos) + '</tr>'
        
        for item in dados:
            html += '<tr>' + ''.join(f'<td>{item.get(c, "")}</td>' for c in campos) + '</tr>'
        return html + '</table>'
    
    elif tipo == 'lista':
        return '<ul class="list-group">' + \
               ''.join(f'<li class="list-group-item">{item.get(campos[1], "")}</li>' for item in dados) + \
               '</ul>'
    
    else:  # Default é label
        return '<div class="ref-label">' + \
               '<br>'.join(item.get(campos[1], "") for item in dados) + \
               '</div>'


def aplicar_mascara_documento(valor):
    """Aplica máscara de CPF ou CNPJ dependendo do tamanho do valor."""
    if not valor:
        return valor
    if len(valor) == 11:
        return f"{valor[:3]}.{valor[3:6]}.{valor[6:9]}-{valor[9:]}"
    elif len(valor) == 14:
        return f"{valor[:2]}.{valor[2:5]}.{valor[5:8]}/{valor[8:12]}-{valor[12:]}"
    return valor               