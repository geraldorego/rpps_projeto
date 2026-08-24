"""
Módulo de helpers para normalização de metadados e compatibilidade retroativa.

Centraliza regras de normalização para campos de estrutura de metadados,
permitindo retrocompatibilidade com valores históricos enquanto normaliza
para um padrão canônico.
"""

import ast
import json
import logging
import re

from django.apps import apps
from django.db import connection

logger = logging.getLogger(__name__)

_SQL_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def get_allowed_table_names():
    """Retorna o conjunto de tabelas conhecidas e autorizadas pelo projeto."""
    nomes = set()

    try:
        from .models import RppsEstrutura
        nomes.update(
            str(v).strip()
            for v in RppsEstrutura.objects.exclude(nome_tabela__isnull=True).exclude(nome_tabela='').values_list('nome_tabela', flat=True)
            if v and str(v).strip()
        )
    except Exception:
        logger.warning("Não foi possível carregar nomes de tabela via RppsEstrutura.")

    for model in apps.get_models():
        if model._meta.app_label == 'app_rpps':
            nomes.add(model.__name__)
            if model._meta.db_table:
                nomes.add(model._meta.db_table)

    return sorted(nomes)


def validate_table_name(nome_tabela, *, allow_schema=False):
    """Valida um identificador de tabela antes de usá-lo em SQL dinâmico."""
    if nome_tabela is None:
        raise ValueError("Nome de tabela ausente.")

    valor = str(nome_tabela).strip()
    if not valor:
        raise ValueError("Nome de tabela vazio.")

    if not _SQL_IDENTIFIER_RE.fullmatch(valor):
        raise ValueError(f"Nome de tabela inválido: {nome_tabela!r}")

    if not allow_schema and '.' in valor:
        raise ValueError(f"Nome de tabela com schema não é permitido: {nome_tabela!r}")

    tabelas_autorizadas = set(get_allowed_table_names())
    if valor not in tabelas_autorizadas and valor.lower() not in {t.lower() for t in tabelas_autorizadas}:
        raise ValueError(f"Tabela não autorizada: {nome_tabela!r}")

    # Validação adicional de existência real no schema consultando informações do banco.
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = %s",
                [valor],
            )
            if not cursor.fetchone():
                raise ValueError(f"Tabela não encontrada no schema: {nome_tabela!r}")
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        logger.warning("Não foi possível confirmar existência no schema para %s: %s", nome_tabela, exc)

    return valor


def get_allowed_columns(table_name):
    """Retorna as colunas autorizadas para uma tabela conhecida do projeto."""
    tabela = validate_table_name(table_name)

    model = None
    for candidate in apps.get_models():
        if candidate._meta.app_label != 'app_rpps':
            continue
        if candidate.__name__ == tabela or candidate._meta.db_table == tabela:
            model = candidate
            break

    if model is not None:
        return [field.name for field in model._meta.fields]

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                [tabela],
            )
            return [row[0] for row in cursor.fetchall()]
    except Exception as exc:
        raise ValueError(f"Não foi possível listar colunas da tabela {tabela!r}: {exc}") from exc


def validate_column_name(table_name, column_name):
    """Valida um identificador de coluna antes de usá-lo em SQL dinâmico."""
    tabela = validate_table_name(table_name)
    if column_name is None:
        raise ValueError(f"Coluna ausente para a tabela {tabela!r}.")

    valor = str(column_name).strip()
    if not valor:
        raise ValueError(f"Coluna vazia para a tabela {tabela!r}.")

    if not _SQL_IDENTIFIER_RE.fullmatch(valor):
        raise ValueError(f"Coluna inválida para a tabela {tabela!r}: {column_name!r}")

    colunas = set(get_allowed_columns(tabela))
    if valor not in colunas and valor.lower() not in {c.lower() for c in colunas}:
        raise ValueError(f"Coluna não autorizada para a tabela {tabela!r}: {column_name!r}")

    return valor


def validate_columns(table_name, columns):
    """Valida uma lista de colunas e retorna a ordem original, sem aceitar identificadores hostis."""
    tabela = validate_table_name(table_name)
    if not columns:
        return []

    validas = []
    for campo in columns:
        validas.append(validate_column_name(tabela, campo))
    return validas


def validate_model_field_name(model, field_name, allow_relation=False):
    """Valida um nome de campo do ORM e rejeita lookup traversal / campos proibidos."""
    if model is None:
        logger.warning("validate_model_field_name: model ausente.")
        return None

    if field_name is None:
        logger.warning("validate_model_field_name: field_name ausente para %s.", model.__name__)
        return None

    valor = str(field_name).strip()
    if not valor:
        logger.warning("validate_model_field_name: field_name vazio para %s.", model.__name__)
        return None

    if valor in {'__', '.', '..'} or '__' in valor or '.' in valor:
        logger.warning("validate_model_field_name: lookup traversal rejeitado para %s: %r", model.__name__, field_name)
        return None

    if not _SQL_IDENTIFIER_RE.fullmatch(valor):
        logger.warning("validate_model_field_name: identificador inválido para %s: %r", model.__name__, field_name)
        return None

    try:
        meta_field = model._meta.get_field(valor)
    except Exception:
        logger.warning("validate_model_field_name: campo não encontrado em %s: %r", model.__name__, field_name)
        return None

    if not allow_relation:
        if hasattr(meta_field, 'many_to_many') and meta_field.many_to_many:
            logger.warning("validate_model_field_name: campo de relacionamento rejeitado em %s: %r", model.__name__, field_name)
            return None
        if hasattr(meta_field, 'many_to_one') and meta_field.many_to_one:
            logger.warning("validate_model_field_name: ForeignKey rejeitado em %s: %r", model.__name__, field_name)
            return None
        if hasattr(meta_field, 'one_to_many') and meta_field.one_to_many:
            logger.warning("validate_model_field_name: relacionamento rejeitado em %s: %r", model.__name__, field_name)
            return None

    return valor


def validate_model_field_names(model, field_names, allow_relation=False):
    """Valida uma lista de nomes de campo do ORM e retorna somente campos seguros."""
    if model is None:
        return []
    if not field_names:
        return []

    validas = []
    for item in field_names:
        valido = validate_model_field_name(model, item, allow_relation=allow_relation)
        if valido:
            validas.append(valido)
    return validas


def resolve_model_target(app_label, model_name):
    """Resolve um modelo do app_rpps usando regras restritas sem whitelist fixa de negócios."""
    if app_label is None or str(app_label).strip() != 'app_rpps':
        logger.warning("resolve_model_target: app_label inválido: %r", app_label)
        return None

    if model_name is None:
        logger.warning("resolve_model_target: model_name ausente para app_label %r", app_label)
        return None

    valor = str(model_name).strip()
    if not valor:
        logger.warning("resolve_model_target: model_name vazio para app_label %r", app_label)
        return None

    if not _SQL_IDENTIFIER_RE.fullmatch(valor):
        logger.warning("resolve_model_target: model_name inválido para %r: %r", app_label, model_name)
        return None

    try:
        model = apps.get_model(app_label=app_label, model_name=valor)
    except Exception:
        logger.warning("resolve_model_target: modelo não encontrado para %s.%s", app_label, valor)
        return None

    if model is None:
        logger.warning("resolve_model_target: modelo ausente para %s.%s", app_label, valor)
        return None

    return model


def safe_model_filter(model, filters):
    """Filtra um dicionário de filtros, removendo chaves inválidas e potencialmente perigosas."""
    if model is None or not isinstance(filters, dict):
        return {}

    seguros = {}
    for chave, valor in filters.items():
        campo_valido = validate_model_field_name(model, chave)
        if campo_valido is None:
            logger.warning("safe_model_filter: campo rejeitado para %s: %r", model.__name__, chave)
            continue
        seguros[campo_valido] = valor
    return seguros


def validate_order_by(table_name, order_by):
    """Valida e normaliza uma cláusula ORDER BY controlada por metadados.

    Aceita entradas como:
      - 'ano_ref'
      - '-mes_ref'
      - 'ano_ref DESC'
      - 'ano_ref DESC, mes_ref ASC'

    Retorna uma cláusula SQL segura com identificadores citados e direção validada.
    """
    tabela = validate_table_name(table_name)
    if order_by is None:
        return ''

    valor = str(order_by).strip()
    if not valor:
        return ''

    partes = [parte.strip() for parte in valor.split(',') if parte.strip()]
    if not partes:
        return ''

    clausulas = []
    for parte in partes:
        match = re.match(r'^(?P<prefix>[+-])?(?P<campo>[A-Za-z_][A-Za-z0-9_]*)(?:\s+(?P<direcao>ASC|DESC))?$', parte, re.IGNORECASE)
        if not match:
            raise ValueError(f"ORDER BY inválido para tabela {tabela!r}: {order_by!r}")

        campo = validate_column_name(tabela, match.group('campo'))
        direcao = (match.group('direcao') or '').upper()
        prefix = match.group('prefix') or ''

        if prefix == '-':
            direcao = 'DESC'
        elif prefix == '+':
            direcao = 'ASC'

        item = connection.ops.quote_name(campo)
        if direcao:
            item = f"{item} {direcao}"
        clausulas.append(item)

    return ', '.join(clausulas)


def parse_referencia_config(tabela_referencia):
    """Converte o DSL legado em uma estrutura canônica e formal.

    Retorna um dict com:
      - tabela: nome do modelo alvo
      - campo_tabela: campo da tabela referenciada
      - campo_tela: campo exibido na tela
      - filtros: dicionário de mapeamento para filtros opcionais
      - dependencias: lista de campos de dependência
    """
    if tabela_referencia is None:
        return {'tabela': None, 'campo_tabela': None, 'campo_tela': None, 'filtros': {}, 'dependencias': []}

    tabela_ref_limpa = str(tabela_referencia).strip()
    if not tabela_ref_limpa:
        return {'tabela': None, 'campo_tabela': None, 'campo_tela': None, 'filtros': {}, 'dependencias': []}

    nome_tabela, campo_tabela, campo_tela = parse_tabela_referencia(tabela_ref_limpa)
    config = {
        'tabela': nome_tabela,
        'campo_tabela': campo_tabela,
        'campo_tela': campo_tela,
        'filtros': {},
        'dependencias': [],
    }

    if not campo_tela:
        return config

    filtros = {}
    dependencias = []
    for parte in str(campo_tela).split(','):
        item = parte.strip()
        if not item:
            continue

        if '=' in item:
            campo_ref, campo_local = [valor.strip() for valor in item.split('=', 1)]
            if campo_ref and campo_local:
                filtros[campo_ref] = campo_local
                dependencias.append(campo_ref)
        else:
            dependencias.append(item)

    if filtros:
        config['filtros'] = filtros
    if dependencias:
        config['dependencias'] = dependencias

    return config


def parse_tabela_referencia(tabela_referencia):
    """
    Extrai nome da tabela, campo da tabela e campo da tela do formato de tabela_referencia.

    Compatível com o DSL usado pelo projeto, sem migrar metadados para JSON.

    Formatos suportados:
    - "Cadastro" -> ("Cadastro", None, None)
    - "Cadastro(CpfCnpj)" -> ("Cadastro", "CpfCnpj", None)
    - "Cadastro(CpfCnpj=CPF)" -> ("Cadastro", "CpfCnpj", "CPF")
    - "GruposColegiados(ano_ref=ano_ref,mes_ref=mesref,TipoFundo=Tipo_fundo)" ->
      ("GruposColegiados", "ano_ref", "ano_ref,mes_ref=mesref,TipoFundo=Tipo_fundo")
    """
    if tabela_referencia is None:
        return (None, None, None)

    tabela_ref_limpa = str(tabela_referencia).strip()
    if not tabela_ref_limpa:
        return (None, None, None)

    if '(' in tabela_ref_limpa and ')' in tabela_ref_limpa:
        try:
            nome_tabela = tabela_ref_limpa.split('(')[0].strip()
            conteudo_parenteses = tabela_ref_limpa.split('(')[1].split(')')[0].strip()

            if not conteudo_parenteses:
                return (nome_tabela, None, None)

            partes = [parte.strip() for parte in conteudo_parenteses.split(',') if parte.strip()]
            if not partes:
                return (nome_tabela, None, None)

            if '=' in conteudo_parenteses:
                primeiro = partes[0]
                if '=' in primeiro:
                    campo_tabela, valor_principal = [item.strip() for item in primeiro.split('=', 1)]
                    if campo_tabela == valor_principal:
                        campo_tela = [valor_principal]
                        campo_tela.extend(partes[1:])
                        return (nome_tabela, campo_tabela, ','.join(campo_tela))

                    campo_tela = [valor_principal]
                    campo_tela.extend(partes[1:])
                    return (nome_tabela, campo_tabela, ','.join(campo_tela))

                return (nome_tabela, primeiro.strip(), None)

            campo_tabela = conteudo_parenteses.strip()
            return (nome_tabela, campo_tabela, None)
        except IndexError:
            logger.warning(f"Formato inválido de tabela_referencia: {tabela_referencia}")
            return (None, None, None)

    return (tabela_ref_limpa, None, None)


def get_referencia_config(estrutura):
    """Retorna a configuração de referência em formato estruturado.

    Prioriza `referencia_config` quando disponível e usa o parser legado como fallback.
    """
    if estrutura is None:
        return {'tabela': None, 'campo_tabela': None, 'campo_tela': None, 'filtros': {}, 'dependencias': []}

    referencia_config = getattr(estrutura, 'referencia_config', None)
    if referencia_config:
        # O campo é armazenado como TextField; pode conter JSON serializado
        # ou, por gravações legadas, o repr de um dict Python (aspas simples).
        if isinstance(referencia_config, dict):
            return referencia_config
        if isinstance(referencia_config, str):
            try:
                config = json.loads(referencia_config)
                if isinstance(config, dict):
                    return config
            except (ValueError, TypeError):
                try:
                    config = ast.literal_eval(referencia_config)
                    if isinstance(config, dict):
                        return config
                except (ValueError, SyntaxError):
                    logger.warning("get_referencia_config: valor inválido em referencia_config: %r", referencia_config)

    tabela_referencia = getattr(estrutura, 'tabela_referencia', None)
    if tabela_referencia:
        return parse_referencia_config(tabela_referencia)

    return {'tabela': None, 'campo_tabela': None, 'campo_tela': None, 'filtros': {}, 'dependencias': []}


def normalize_reference_name(value):
    """Normaliza nomes de referência para comparar aliases equivalentes do DSL."""
    if value is None:
        return ''
    return re.sub(r'[^a-z0-9]+', '', str(value).strip().lower())


def parse_referencia_dependencias(tabela_referencia):
    """Extrai o mapeamento {campo_ref: campo_local} do DSL de referência."""
    if tabela_referencia is None:
        return {}

    valor = str(tabela_referencia).strip()
    if not valor or '(' not in valor or ')' not in valor:
        return {}

    _, _, campo_tela = parse_tabela_referencia(valor)
    if not campo_tela:
        return {}

    dependencias = {}
    for parte in campo_tela.split(','):
        parte = parte.strip()
        if not parte or '=' not in parte:
            continue
        campo_tabela, campo_local = [item.strip() for item in parte.split('=', 1)]
        if campo_tabela and campo_local:
            dependencias[campo_tabela] = campo_local
    return dependencias


# Mapeamento de valores históricos/conhecidos para formato canônico
CHAVE_TIPO_MAPPING = {
    # PrimaryKey - todas as variações
    'primarykey': 'primary',
    'primary': 'primary',
    'pk': 'primary',
    
    # ForeignKey - todas as variações
    'foreignkey': 'foreign',
    'foreign': 'foreign',
    'fk': 'foreign',
    
    # ForeignKey Composite (se utilizado)
    'foreignkeycomposite': 'foreign_composite',
    'foreign_composite': 'foreign_composite',
    'fk_composite': 'foreign_composite',
    
    # Outros tipos suportados (se existirem no projeto)
    'unique': 'unique',
    'index': 'index',
}


def normalize_chave_tipo(valor):
    """
    Normaliza valores de tipo_chave_blur para formato canônico.
    
    Aceita variações históricas e maiúsculas/minúsculas,
    retornando sempre o valor canônico em minúsculas.
    
    Args:
        valor (str, None): Valor bruto de tipo_chave_blur do banco ou formulário
        
    Returns:
        str: Valor normalizado ('primary', 'foreign', 'foreign_composite', 'unique', 'index', etc.)
             ou None se valor for None/vazio
    
    Comportamento:
        - None/vazio retorna None
        - Espaços em branco são removidos (trim)
        - Maiúsculas/minúsculas são normalizadas
        - Valores históricos (PrimaryKey, ForeignKey) são mapeados corretamente
        - Valores desconhecidos retornam o próprio valor normalizado (sem exceção)
        
    Exemplos:
        >>> normalize_chave_tipo('PrimaryKey')
        'primary'
        
        >>> normalize_chave_tipo('ForeignKey')
        'foreign'
        
        >>> normalize_chave_tipo('primary')
        'primary'
        
        >>> normalize_chave_tipo('  ForeignKey  ')
        'foreign'
        
        >>> normalize_chave_tipo(None)
        
        >>> normalize_chave_tipo('')
        
        >>> normalize_chave_tipo('unknown_type')
        'unknown_type'
    """
    # Trata None e strings vazias
    if valor is None or valor == '':
        return None
    
    # Converte para string se necessário, remove espaços e converte para minúsculas
    valor_normalizado = str(valor).strip().lower()
    
    # Se está vazio depois de trim, retorna None
    if not valor_normalizado:
        return None
    
    # Busca no mapeamento de valores conhecidos
    if valor_normalizado in CHAVE_TIPO_MAPPING:
        resultado = CHAVE_TIPO_MAPPING[valor_normalizado]
        logger.debug(f"[NORMALIZE_CHAVE_TIPO] '{valor}' → '{resultado}'")
        return resultado
    
    # Se não encontrou, retorna o valor normalizado (lowercase + trim)
    # sem lançar exceção
    logger.warning(
        f"[NORMALIZE_CHAVE_TIPO] Valor desconhecido: '{valor}' "
        f"(normalizado para '{valor_normalizado}'). "
        f"Valores conhecidos: {list(CHAVE_TIPO_MAPPING.values())}"
    )
    return valor_normalizado


def is_primary_key_field(tipo_chave):
    """
    Verifica se um campo é do tipo chave primária (retrocompatível).
    
    Args:
        tipo_chave (str, None): Valor de tipo_chave_blur
        
    Returns:
        bool: True se é PrimaryKey/primary, False caso contrário
        
    Exemplos:
        >>> is_primary_key_field('PrimaryKey')
        True
        
        >>> is_primary_key_field('primary')
        True
        
        >>> is_primary_key_field('ForeignKey')
        False
        
        >>> is_primary_key_field(None)
        False
    """
    normalizado = normalize_chave_tipo(tipo_chave)
    return normalizado == 'primary'


def is_foreign_key_field(tipo_chave):
    """
    Verifica se um campo é do tipo chave estrangeira (retrocompatível).
    
    Args:
        tipo_chave (str, None): Valor de tipo_chave_blur
        
    Returns:
        bool: True se é ForeignKey/foreign, False caso contrário
        
    Exemplos:
        >>> is_foreign_key_field('ForeignKey')
        True
        
        >>> is_foreign_key_field('foreign')
        True
        
        >>> is_foreign_key_field('PrimaryKey')
        False
        
        >>> is_foreign_key_field(None)
        False
    """
    normalizado = normalize_chave_tipo(tipo_chave)
    return normalizado in ('foreign', 'foreign_composite')


def is_composite_foreign_key_field(tipo_chave):
    """
    Verifica se um campo é do tipo chave estrangeira composta.
    
    Args:
        tipo_chave (str, None): Valor de tipo_chave_blur
        
    Returns:
        bool: True se é ForeignKeyComposite/foreign_composite, False caso contrário
    """
    normalizado = normalize_chave_tipo(tipo_chave)
    return normalizado == 'foreign_composite'
