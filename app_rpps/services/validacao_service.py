from app_rpps.metadata_helpers import validate_model_field_name, validate_model_field_names, safe_model_filter


def validar_campo_orm(model, field_name):
    """Valida um campo do ORM usando as regras centrais do metadata_helpers."""
    return validate_model_field_name(model, field_name)


def validar_lista_campos_orm(model, field_names):
    """Valida uma lista de campos do ORM e retorna somente os seguros."""
    return validate_model_field_names(model, field_names)


def safe_filter(model, filters):
    """Filtra um dicionário de filtros mantendo somente chaves válidas."""
    return safe_model_filter(model, filters)
