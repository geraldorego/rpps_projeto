from django import template
import json

from app_rpps.services.referencia_service import build_referencia_filters

register = template.Library()

@register.filter
def add_class(field, css_class):
    """Adiciona classe CSS a um campo de formulário"""
    return field.as_widget(attrs={"class": css_class})

@register.filter
def is_checkbox(field):
    """Verifica se o campo é um checkbox"""
    return field.field.widget.__class__.__name__ == "CheckboxInput"

@register.simple_tag
def field_type(field):
    """Retorna o tipo do campo"""
    return field.field.widget.__class__.__name__.lower()

@register.filter
def get_item(dictionary, key):
    """Retorna o valor de um dicionário pela chave"""
    return dictionary.get(key)

@register.filter
def get_attribute(obj, attr_name):
    """Retorna o valor de um atributo de um objeto"""
    return getattr(obj, attr_name, None)

@register.filter
def get_dict_value(dictionary, key):
    """Retorna o valor de um dicionário pela chave"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def jsonify(value):
    """Converte um valor Python para JSON string"""
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return '{}'

@register.simple_tag
def render_fk_field_with_mapping(field, field_name, fk_mappings):
    """
    Renderiza campo FK com atributos data-* para mapeamento de campos relacionados
    
    Args:
        field: Campo do formulário Django
        field_name: Nome do campo
        fk_mappings: Dicionário com mapeamentos FK do contexto
    
    Returns:
        HTML do campo com atributos data-*
    """
    attrs = {}
    
    # Todos os campos com tabela_referencia precisam do handler de blur.
    if field_name in fk_mappings:
        mapping_info = fk_mappings[field_name]
        
        attrs['data-fk-field'] = field_name
        attrs['data-tabela-ref'] = mapping_info.get('tabela_referencia', '')
        attrs['data-fk-search-field'] = mapping_info.get('campo_busca_referencia', '')
        ref_dsl = mapping_info.get('tabela_referencia_dsl') or mapping_info.get('tabela_referencia', '')
        if ref_dsl:
            attrs['data-fk-deps'] = json.dumps(build_referencia_filters(ref_dsl))
        
        # Converte o mapeamento para JSON string
        mapping_dict = mapping_info.get('mapping', {})
        if mapping_dict:
            attrs['data-field-mapping'] = json.dumps(mapping_dict)
    
    # Adiciona classes CSS padrão
    css_classes = field.field.widget.attrs.get('class', '')
    if 'form-select' not in css_classes:
        css_classes += ' form-select'
    attrs['class'] = css_classes.strip()
    
    return field.as_widget(attrs=attrs)
