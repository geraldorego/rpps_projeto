import ast
import json
import logging
import re

from django.db import IntegrityError, transaction

from app_rpps.metadata_helpers import normalize_chave_tipo, validate_model_field_name
from app_rpps.models import RppsEstrutura

logger = logging.getLogger(__name__)


def _is_generated_primary_key(field):
    return field.primary_key and (
        field.auto_created
        or field.get_internal_type() in {'AutoField', 'BigAutoField', 'SmallAutoField'}
    )


def parse_copy_action_parameters(raw_parameters):
    if isinstance(raw_parameters, dict):
        parameters = raw_parameters
    else:
        try:
            parameters = json.loads(raw_parameters or '')
        except (TypeError, ValueError) as exc:
            raise ValueError('Parâmetros de cópia ausentes ou inválidos.') from exc

    if not isinstance(parameters, dict) or parameters.get('tipo') != 'periodo':
        raise ValueError('A ação de cópia deve usar tipo="periodo".')

    normalize_period_field_specs(parameters.get('campos_periodo'))
    return parameters


def normalize_period_field_specs(raw_fields):
    """Converte campos_periodo em [{'name','type','size'}]; aceita [nome, tipo, tamanho] ou só o nome."""
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ValueError('Configure ao menos um campo em campos_periodo.')

    specs = []
    for item in raw_fields:
        if isinstance(item, str):
            name, field_type, size = item, None, None
        elif isinstance(item, (list, tuple)) and 1 <= len(item) <= 3:
            name = item[0]
            field_type = item[1] if len(item) > 1 else None
            size = item[2] if len(item) > 2 else None
        else:
            raise ValueError('Cada item de campos_periodo deve ser [nome_campo, tipo_campo, tamanho].')

        if not isinstance(name, str) or not name.strip():
            raise ValueError('Nome de campo inválido em campos_periodo.')
        if field_type is not None and (not isinstance(field_type, str) or not field_type.strip()):
            raise ValueError(f'Tipo inválido para o campo {name!r} em campos_periodo.')
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size <= 0):
            raise ValueError(f'Tamanho inválido para o campo {name!r} em campos_periodo.')

        specs.append({
            'name': name.strip(),
            'type': field_type.strip().lower() if field_type else None,
            'size': size,
        })
    return specs


def get_period_field_names(parameters):
    return [spec['name'] for spec in normalize_period_field_specs(parameters.get('campos_periodo'))]


_TYPE_ALIASES = {'integer': 'int', 'numeric': 'decimal', 'float': 'decimal', 'char': 'varchar'}


def _canonical_type(value):
    text = str(value or '').strip().lower()
    return _TYPE_ALIASES.get(text, text)


def validate_period_fields_metadata(model, table_name, parameters):
    """Valida os campos de período contra o model e RppsEstrutura; a configuração do CRUD-C prevalece só na apresentação."""
    specs = normalize_period_field_specs(parameters.get('campos_periodo'))
    structures = {
        structure.nome_campo: structure
        for structure in RppsEstrutura.objects.filter(
            nome_tabela__in={table_name, model.__name__, model._meta.db_table}
        )
    }

    validated = []
    for spec in specs:
        name = validate_model_field_name(model, spec['name'])
        if not name:
            raise ValueError(f"Campo de período inválido: {spec['name']!r}.")
        structure = structures.get(name)
        if structure is None:
            raise ValueError(f'Campo de período {name!r} não está configurado em RppsEstrutura.')

        configured_type = spec['type'] or _canonical_type(structure.tipo_campo)
        configured_size = spec['size'] or structure.tamanho
        if spec['type'] and _canonical_type(spec['type']) != _canonical_type(structure.tipo_campo):
            logger.warning(
                'CRUD-C %s.%s: tipo %r difere de RppsEstrutura (%r); usando o configurado no modal.',
                table_name, name, spec['type'], structure.tipo_campo,
            )
        if spec['size'] and spec['size'] != structure.tamanho:
            logger.warning(
                'CRUD-C %s.%s: tamanho %r difere de RppsEstrutura (%r); usando o configurado no modal.',
                table_name, name, spec['size'], structure.tamanho,
            )

        validated.append({
            'name': name,
            'type': _canonical_type(configured_type),
            'size': configured_size,
            'label': structure.label_campo,
        })
    return validated


def _parse_key_field_names(raw_value):
    if not raw_value:
        return []
    text = str(raw_value).strip()
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        parsed = text.strip('()')
    if isinstance(parsed, str):
        parsed = [part.strip() for part in parsed.split(',') if part.strip()]
    if isinstance(parsed, (list, tuple, set)):
        return [str(field).strip() for field in parsed if str(field).strip()]
    return []


def resolve_copy_key_sets(model, table_name):
    key_sets = []

    metadata = RppsEstrutura.objects.filter(nome_tabela__in={table_name, model.__name__, model._meta.db_table})
    for structure in metadata:
        key_type = normalize_chave_tipo(structure.tipo_chave_blur)
        if key_type in {'primary', 'unique'}:
            fields = _parse_key_field_names(structure.campo_chave_blur)
            key_sets.append(tuple(fields) if fields else (structure.nome_campo,))

    unique_together = model._meta.unique_together or ()
    for constraint_fields in unique_together:
        if isinstance(constraint_fields, str):
            constraint_fields = (constraint_fields,)
        key_sets.append(tuple(constraint_fields))

    for constraint in model._meta.constraints:
        fields = getattr(constraint, 'fields', None)
        if fields:
            key_sets.append(tuple(fields))

    primary_key = model._meta.pk
    if primary_key and not _is_generated_primary_key(primary_key):
        key_sets.append((primary_key.name,))

    valid_sets = []
    for candidate in key_sets:
        validated = []
        for field_name in candidate:
            field_name_valid = validate_model_field_name(model, field_name, allow_relation=True)
            if field_name_valid:
                field = model._meta.get_field(field_name_valid)
                if not _is_generated_primary_key(field):
                    validated.append(field_name_valid)
        normalized = tuple(dict.fromkeys(validated))
        if normalized and normalized not in valid_sets:
            valid_sets.append(normalized)

    if not valid_sets:
        raise ValueError('Não foi possível identificar chaves para evitar registros duplicados.')
    return valid_sets


def _normalize_period_values(model, period_specs, values):
    normalized = {}
    for spec in period_specs:
        field_name = spec['name']
        valid_name = validate_model_field_name(model, field_name)
        if not valid_name:
            raise ValueError(f'Campo de período inválido: {field_name!r}.')
        raw_value = values.get(field_name)
        if raw_value is None or str(raw_value).strip() == '':
            raise ValueError(f'Informe o valor do período para {field_name}.')

        text = str(raw_value).strip()
        size = spec.get('size')
        label = spec.get('label') or field_name
        # O tamanho do CRUD-C é a quantidade máxima de dígitos/caracteres, não o valor máximo.
        if spec.get('type') == 'int' and not re.fullmatch(r'[0-9]+', text):
            raise ValueError(f'{label} aceita somente dígitos.')
        if spec.get('type') in {'int', 'varchar', 'text'} and size and len(text) > size:
            raise ValueError(f'{label} aceita no máximo {size} caractere(s).')
        normalized[valid_name] = model._meta.get_field(valid_name).to_python(text)
    return normalized


def preview_period_copy(model, table_name, parameters, source_values, destination_values):
    parameters = parse_copy_action_parameters(parameters)
    period_specs = validate_period_fields_metadata(model, table_name, parameters)
    period_fields = [spec['name'] for spec in period_specs]
    source_period = _normalize_period_values(model, period_specs, source_values)
    destination_period = _normalize_period_values(model, period_specs, destination_values)
    key_sets = resolve_copy_key_sets(model, table_name)
    source_queryset = model.objects.filter(**source_period)

    return {
        'found': source_queryset.count(),
        'key_sets': key_sets,
        'source_period': source_period,
        'destination_period': destination_period,
        'period_fields': period_fields,
        'parameters': parameters,
    }


def _record_exists_for_destination(model, source_record, key_sets, destination_period):
    for key_fields in key_sets:
        lookup = {field_name: getattr(source_record, field_name) for field_name in key_fields}
        lookup.update(destination_period)
        if model.objects.filter(**lookup).exists():
            return True
    return False


def copy_period_records(model, table_name, parameters, source_values, destination_values):
    preview = preview_period_copy(model, table_name, parameters, source_values, destination_values)
    source_records = list(model.objects.filter(**preview['source_period']))
    copied = 0
    ignored = 0
    errors = 0
    error_messages = []

    for source_record in source_records:
        if _record_exists_for_destination(model, source_record, preview['key_sets'], preview['destination_period']):
            ignored += 1
            continue

        values = {}
        for field in model._meta.concrete_fields:
            if _is_generated_primary_key(field):
                continue
            value = preview['destination_period'].get(field.name, getattr(source_record, field.name))
            values[field.name] = value

        try:
            with transaction.atomic():
                model.objects.create(**values)
            copied += 1
        except IntegrityError as exc:
            if _record_exists_for_destination(model, source_record, preview['key_sets'], preview['destination_period']):
                ignored += 1
            else:
                errors += 1
                logger.exception('Erro de integridade ao copiar registro %s.%s', table_name, source_record.pk)
                if len(error_messages) < 10:
                    error_messages.append(str(exc))
        except Exception as exc:
            errors += 1
            logger.exception('Erro ao copiar registro %s.%s', table_name, source_record.pk)
            if len(error_messages) < 10:
                error_messages.append(str(exc))

    return {
        'found': preview['found'],
        'copied': copied,
        'ignored': ignored,
        'errors': errors,
        'error_messages': error_messages,
    }