from app_rpps.metadata_helpers import validate_model_field_name


def check_record_existe(model, campo_pk_ref, valor):
    """Verifica se um valor informado existe no campo PK de referência do modelo."""
    if model is None or not campo_pk_ref or valor in (None, ''):
        return False

    campo_validado = validate_model_field_name(model, campo_pk_ref)
    if not campo_validado:
        return False

    valor_limpo = str(valor).strip()
    if not valor_limpo:
        return False

    return model.objects.filter(**{campo_validado: valor_limpo}).exists()


def get_or_create_check(model, campos):
    """Busca ou cria um registro utilizando somente campos validados do ORM."""
    if model is None or not isinstance(campos, dict):
        return None, False

    campos_validos = {}
    for nome_campo, valor in campos.items():
        if valor in (None, ''):
            continue
        campo_validado = validate_model_field_name(model, nome_campo)
        if campo_validado:
            campos_validos[campo_validado] = valor

    if not campos_validos:
        return None, False

    return model.objects.get_or_create(**campos_validos)
