from app_rpps.metadata_helpers import (
    parse_referencia_dependencias,
    validate_model_field_name,
    safe_model_filter,
)


def build_referencia_filters(tabela_referencia):
    """Extrai filtros de referência a partir do DSL da tabela_referencia."""
    if tabela_referencia is None:
        return {}
    return parse_referencia_dependencias(tabela_referencia)


def get_referencia_options(model_ref, campo_display, search_term=None, filtros=None):
    """Obtém opções seguras para campos de referência a partir de um modelo e de um campo exibido."""
    campo_validado = validate_model_field_name(model_ref, campo_display)
    if not campo_validado:
        return []

    queryset = model_ref.objects.all()
    if search_term:
        queryset = queryset.filter(**{f'{campo_validado}__icontains': search_term})
    if filtros:
        queryset = queryset.filter(**safe_model_filter(model_ref, filtros))

    return queryset.values('id', campo_validado).order_by(campo_validado)


def get_referencia_display(model_ref, campo_display, pk):
    """Retorna o valor de exibição de um registro de referência."""
    campo_validado = validate_model_field_name(model_ref, campo_display)
    if not campo_validado:
        return ''

    filtro_pk = {model_ref._meta.pk.name: pk}
    record = model_ref.objects.filter(**filtro_pk).first()
    if record is None:
        return ''
    return getattr(record, campo_validado, '')
