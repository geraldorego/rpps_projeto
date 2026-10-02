import ast
import json
import re

from django.apps import apps

def _normalized_words(value):
    separated = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(value or ''))
    words = re.findall(r'[A-Za-z0-9]+', separated)
    return {word.lower()[:-1] if word.lower().endswith('s') else word.lower() for word in words if len(word) > 3}

from app_rpps.metadata_helpers import (
    get_referencia_config,
    parse_tabela_referencia,
    validate_table_name,
    validate_model_field_name,
    safe_model_filter,
)


def build_referencia_filters(tabela_referencia):
    """Retorna dependências adicionais do DSL, excluindo o par chave=campo local."""
    return parse_reference(tabela_referencia).get('filtros', {})


def _display_field_name(value, local_field=None):
    """Aceita display simples, JSON ou mapa textual local=campo relacionado."""
    if not value:
        return None
    if isinstance(value, dict):
        mapping = value
    else:
        text = str(value).strip()
        try:
            mapping = json.loads(text)
        except (TypeError, ValueError):
            mapping = None
        if isinstance(mapping, dict):
            pass
        elif '=' in text:
            mapping = {}
            for item in text.split(','):
                if '=' in item:
                    local_name, reference_name = item.split('=', 1)
                    mapping[local_name.strip()] = reference_name.strip()
        else:
            return text or None

    if not isinstance(mapping, dict) or not mapping:
        return None
    if local_field and mapping.get(local_field):
        return str(mapping[local_field]).strip()
    return str(next(iter(mapping.values()))).strip()


def _prefer_descriptive_display(config, model_ref):
    """Resolve display literal ou campo enumerado descritivo, sem usar a chave como rótulo."""
    key_field = config.get('campo_chave')
    display_field = config.get('campo_display')

    model_fields = {field.name for field in model_ref._meta.fields}
    if display_field in model_fields and display_field != key_field:
        return display_field

    for candidate in ('Descricao', 'descricao', 'description', 'Description', 'Nome', 'nome'):
        if candidate in model_fields and candidate != key_field:
            return candidate

    metadata = _get_reference_structure_fields(model_ref)
    excluded = {key_field, *(config.get('filtros') or {}).keys()}
    enum_fields = [
        item for item in metadata
        if item.get('nome_campo') in model_fields - excluded and item.get('entrada_espec')
    ]
    if len(enum_fields) == 1:
        return enum_fields[0]['nome_campo']

    model_words = set()
    for label in (
        model_ref.__name__,
        model_ref._meta.db_table,
        getattr(model_ref._meta, 'verbose_name', ''),
        getattr(model_ref._meta, 'verbose_name_plural', ''),
    ):
        model_words.update(_normalized_words(label))
    scored_fields = [
        (len(model_words & _normalized_words(item.get('label_campo'))), item)
        for item in enum_fields
    ]
    best_score = max((score for score, _ in scored_fields), default=0)
    best_matches = [item for score, item in scored_fields if score == best_score and score > 0]
    if len(best_matches) == 1:
        return best_matches[0]['nome_campo']

    preferred = [
        item for item in enum_fields
        if any(token in str(item.get('nome_campo', '')).lower() for token in ('descricao', 'nome', 'tipo'))
        or any(token in str(item.get('label_campo', '')).lower() for token in ('descri', 'nome', 'tipo'))
    ]
    if len(preferred) == 1:
        return preferred[0]['nome_campo']

    return display_field if display_field in model_fields else key_field


def _get_reference_structure_fields(model_ref):
    """Lê opções declaradas em RppsEstrutura para os campos do modelo relacionado."""
    from app_rpps.models import RppsEstrutura

    table_names = {model_ref.__name__, model_ref._meta.db_table}
    return list(
        RppsEstrutura.objects.filter(nome_tabela__in=table_names)
        .exclude(entrada_espec__isnull=True)
        .exclude(entrada_espec='')
        .values('nome_campo', 'label_campo', 'entrada_espec')
    )


def _parse_reference_choice_labels(value):
    """Converte entrada_espec (JSON, literal de tuplas ou pares simples) em labels."""
    if not value:
        return {}
    try:
        options = json.loads(value)
    except (TypeError, ValueError):
        try:
            options = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            options = {}

    if isinstance(options, dict):
        return {str(key): str(label) for key, label in options.items()}
    if isinstance(options, (list, tuple)):
        labels = {}
        for item in options:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                labels[str(item[0])] = str(item[1])
        if labels:
            return labels

    labels = {}
    for item in str(value).split(','):
        if ':' in item:
            key, label = item.split(':', 1)
            labels[key.strip()] = label.strip()
    return labels


def _get_reference_display_choices(model_ref, display_field):
    """Retorna labels configurados para um campo enumérico de display."""
    try:
        field_type = model_ref._meta.get_field(display_field).get_internal_type()
    except (AttributeError, LookupError):
        return {}
    if field_type not in {'IntegerField', 'SmallIntegerField', 'BigIntegerField', 'PositiveIntegerField', 'PositiveSmallIntegerField'}:
        return {}

    metadata = _get_reference_structure_fields(model_ref)
    field_config = next((item for item in metadata if item.get('nome_campo') == display_field), None)
    return _parse_reference_choice_labels(field_config.get('entrada_espec')) if field_config else {}


def parse_reference(reference):
    """Normaliza uma string DSL ou RppsEstrutura em uma configuração única.

    No DSL, o primeiro par dentro dos parênteses define campo-chave=campo-local;
    os pares seguintes são filtros/dependências da consulta.
    """
    structure = reference if not isinstance(reference, str) else None
    dsl = getattr(structure, 'tabela_referencia', None) if structure else reference
    base = get_referencia_config(structure) if structure else get_referencia_config(
        type('ReferenceConfig', (), {'tabela_referencia': dsl, 'referencia_config': None})()
    )
    has_structured_config = bool(getattr(structure, 'referencia_config', None)) if structure else False

    tabela, parsed_key, parsed_local = parse_tabela_referencia(dsl)
    config_value = base if isinstance(base, dict) else {}
    table_name = config_value.get('tabela') or tabela
    key_field = config_value.get('campo_chave') or config_value.get('campo_tabela') or parsed_key
    local_field = config_value.get('campo_local')

    pairs = []
    if dsl and '(' in str(dsl) and ')' in str(dsl):
        content = str(dsl).split('(', 1)[1].split(')', 1)[0]
        pairs = [part.strip() for part in content.split(',') if part.strip()]

    if pairs and '=' in pairs[0] and not has_structured_config:
        first_left, first_right = [part.strip() for part in pairs[0].split('=', 1)]
        if first_left == first_right:
            key_field = None
            local_field = None

    filters = {}
    mappings = []
    for index, item in enumerate(pairs):
        if '=' in item:
            reference_field, local_name = [part.strip() for part in item.split('=', 1)]
        else:
            reference_field = local_name = item
        if reference_field and local_name:
            mappings.append((reference_field, local_name))
        if index == 0:
            same_name_filter = '=' in item and reference_field == local_name and not has_structured_config
            if not same_name_filter:
                if not key_field:
                    key_field = reference_field
                if not local_field:
                    local_field = local_name
                continue
        if reference_field and local_name:
            filters[reference_field] = local_name

    configured_filters = config_value.get('filtros')
    if isinstance(configured_filters, dict):
        filters.update(configured_filters)

    display_setting = getattr(structure, 'campo_display_referencia', None) if structure else None
    display_field = (
        config_value.get('campo_display')
        or _display_field_name(display_setting, local_field)
        or key_field
    )

    return {
        'tabela': table_name,
        'campo_chave': key_field,
        'campo_local': local_field,
        'campo_display': display_field,
        'filtros': filters,
        'dependencias': list(filters.values()),
        'mapeamentos': mappings,
    }


def resolve_reference_model(config):
    """Resolve somente modelos do app_rpps após validar o identificador da tabela."""
    if not config or not config.get('tabela'):
        raise ValueError('Tabela de referência ausente.')
    table_name = validate_table_name(config['tabela'])
    for model in apps.get_models():
        if model._meta.app_label != 'app_rpps':
            continue
        if model.__name__.lower() == table_name.lower() or model._meta.db_table.lower() == table_name.lower():
            return model
    raise ValueError(f'Modelo de referência inválido: {table_name!r}.')


def validate_reference_config(reference, model_ref=None):
    """Valida tabela, chave, display e dependências de uma referência dinâmica."""
    config = parse_reference(reference) if not isinstance(reference, dict) else dict(reference)
    model_ref = model_ref or resolve_reference_model(config)

    if not config.get('campo_chave'):
        candidate_fields = {field.name for field in model_ref._meta.fields}
        config['campo_chave'] = 'Codigo' if 'Codigo' in candidate_fields else model_ref._meta.pk.name

    config['campo_display'] = _prefer_descriptive_display(config, model_ref)

    for config_name, message in (
        ('campo_chave', 'Campo-chave'),
        ('campo_display', 'Campo display'),
    ):
        field_name = config.get(config_name)
        if not field_name:
            if config_name == 'campo_display':
                config[config_name] = config['campo_chave']
                continue
            raise ValueError(f'{message} da referência ausente.')
        validated = validate_model_field_name(model_ref, field_name)
        if not validated:
            raise ValueError(f'{message} inválido: {field_name!r}.')
        config[config_name] = validated

    validated_filters = {}
    for reference_field, local_field in (config.get('filtros') or {}).items():
        reference_field_valid = validate_model_field_name(model_ref, reference_field)
        if not reference_field_valid:
            raise ValueError(f'Campo de filtro inválido: {reference_field!r}.')
        validated_filters[reference_field_valid] = str(local_field).strip()
    config['filtros'] = validated_filters
    config['modelo'] = model_ref
    return config


def resolve_reference_display(reference, record):
    """Obtém o valor de display após validar o campo contra o modelo relacionado."""
    config = validate_reference_config(reference, model_ref=record.__class__)
    return getattr(record, config['campo_display'])


def find_reference_record(reference, key_value, filtros=None):
    """Busca um registro pelo campo-chave configurado, usando parâmetros do ORM."""
    config = validate_reference_config(reference)
    if key_value in (None, ''):
        return config, None
    query = {config['campo_chave']: key_value}
    query.update(safe_model_filter(config['modelo'], filtros or {}))
    return config, config['modelo'].objects.filter(**query).first()


def normalize_reference_key(value, document=False):
    """Normaliza chaves recebidas; remove máscara somente em campos documentais."""
    if value is None:
        return ''
    text = str(value).strip()
    return re.sub(r'\D', '', text) if document else text


def get_reference_options(reference, search_term=None, filtros=None):
    """Retorna pares (chave configurada, display configurado) para ChoiceField."""
    config = validate_reference_config(reference)
    queryset = config['modelo'].objects.all()

    provided_filters = dict(filtros or {})
    effective_filters = {}
    for reference_field, local_field in config['filtros'].items():
        if local_field not in provided_filters or provided_filters[local_field] in (None, ''):
            return []
        effective_filters[reference_field] = provided_filters[local_field]
    if not config['filtros']:
        effective_filters = provided_filters
    safe_filters = safe_model_filter(config['modelo'], effective_filters)
    if safe_filters:
        queryset = queryset.filter(**safe_filters)

    if search_term:
        queryset = queryset.filter(**{f"{config['campo_display']}__icontains": search_term})
    records = queryset.values_list(config['campo_chave'], config['campo_display']).order_by(config['campo_display'])
    display_choices = _get_reference_display_choices(config['modelo'], config['campo_display'])
    return [
        (key, display_choices.get(str(display), str(display)) if display is not None else str(key))
        for key, display in records
    ]


def get_referencia_options(model_ref, campo_display=None, search_term=None, filtros=None):
    """Compatibilidade retroativa para chamadores do antigo helper."""
    key_field = model_ref._meta.pk.name
    config = {
        'tabela': model_ref.__name__,
        'campo_chave': key_field,
        'campo_local': None,
        'campo_display': campo_display or key_field,
        'filtros': {},
    }
    return [
        {'id': key, key_field: key, config['campo_display']: display}
        for key, display in get_reference_options(config, search_term, filtros)
    ]


def get_referencia_display(model_ref, campo_display, pk):
    """Compatibilidade retroativa para obter display pela PK do modelo."""
    config = {
        'tabela': model_ref.__name__,
        'campo_chave': model_ref._meta.pk.name,
        'campo_local': None,
        'campo_display': campo_display or model_ref._meta.pk.name,
        'filtros': {},
        'modelo': model_ref,
    }
    try:
        validated = validate_reference_config(config, model_ref=model_ref)
    except ValueError:
        return ''
    record = model_ref.objects.filter(**{validated['campo_chave']: pk}).first()
    return getattr(record, validated['campo_display'], '') if record else ''
