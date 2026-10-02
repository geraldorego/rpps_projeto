import re
import ast
import json
import logging
from django import forms
from django.apps import apps
from django.core.validators import RegexValidator
from django.db import connection
from django.urls import reverse
from django.core.cache import cache
from .models import RppsEstrutura
from django.core.exceptions import ValidationError
from .metadata_helpers import (
    is_primary_key_field,
    normalize_reference_name,
)
from .services.referencia_service import (
    get_reference_options,
    parse_reference,
    resolve_reference_model,
    validate_reference_config,
)

logger = logging.getLogger(__name__)

class DynamicFormGenerator:
    def __init__(self, tabela, initial=None):
        self.tabela = tabela
        self.initial = initial or {}
        self.estrutura_campos = self._load_estrutura_campos()
        self.campos_chave = self._get_campos_chave()
        self.max_ordem_blur = self._get_max_ordem_blur()

    def _load_estrutura_campos(self):
        cache_key = f'estrutura_campos_{self.tabela}'
        campos = cache.get(cache_key)

        if campos is None:
            campos = RppsEstrutura.objects.filter(nome_tabela=self.tabela).order_by('ordem_campo')
            cache.set(cache_key, campos, timeout=60 * 15)

        return {campo.nome_campo: campo for campo in campos}

    def _get_campos_chave(self):
        campos_chave = []
        for campo in self.estrutura_campos.values():
            if campo.campo_chave_blur and campo.campo_blur:
                try:
                    conteudo = campo.campo_chave_blur.strip().strip('()')
                    campos = [item.strip() for item in conteudo.split(',') if item.strip()]
                    campos_chave.extend(campos)
                except Exception as e:
                    logger.error(f"Erro ao processar campo_chave_blur em {campo.nome_campo}: {str(e)}")
        return list(set(campos_chave))

    def _get_max_ordem_blur(self):
        max_ordem = 0
        for campo in self.estrutura_campos.values():
            if campo.campo_blur and is_primary_key_field(campo.tipo_chave_blur):
                max_ordem = max(max_ordem, campo.ordem_campo)
        return max_ordem

    def _get_field_attrs(self, campo):
        largura = f'width:{max(min(campo.tamanho, 30), 10) * 15}px;'
        classe = 'form-control'

        # Estilização dos campos chave com base na ordem - REMOVIDO TEMPORARIAMENTE PARA TESTE
        # if campo.ordem_campo <= self.max_ordem_blur:
        #     classe += ' campo-chave campo-chave-total'  # Aplica estilo visual

        attrs = {
            'class': classe,
            'id': f'id_{campo.nome_campo}',
            'style': largura,
            'data-ordem': campo.ordem_campo
        }

        # Máscara para CPF/CNPJ
        if campo.tipo_campo.lower() == 'varchar5':
            attrs['data-mask-cpfcnpj'] = 'true'
            attrs['maxlength'] = 18  # Permite digitar com máscara (ex: 00.000.000/0000-00)

        # Campos com ação de blur (verificação dinâmica via JavaScript)
        if campo.campo_blur:
            try:
                check_url = reverse('check_record', kwargs={'tabela': self.tabela})
                attrs.update({
                    'data-check-url': check_url,
                    'data-campo-blur': 'true'
                })
                
                # IMPORTANTE: Usa get_campos_chave() que inclui unique_together automaticamente
                # Importação local para evitar circular import
                try:
                    from .views import get_campos_chave
                    todos_campos_chave = get_campos_chave(self.tabela)
                    if todos_campos_chave:
                        attrs['data-campos-relacionados'] = ','.join(todos_campos_chave)
                        logger.info(f"[FORMS] Campo blur '{campo.nome_campo}': campos relacionados = {todos_campos_chave}")
                except Exception as e:
                    # Fallback para campo_chave_blur se get_campos_chave falhar
                    logger.warning(f"Erro ao obter campos chave via get_campos_chave: {e}")
                    if campo.campo_chave_blur:
                        conteudo = campo.campo_chave_blur.strip()
                        if conteudo.startswith('(') and conteudo.endswith(')'):
                            conteudo = conteudo[1:-1]
                        campos = [c.strip() for c in conteudo.split(',') if c.strip()]
                        attrs['data-campos-relacionados'] = ','.join(campos)
                        
            except Exception as e:
                # Não falhar o render por causa de reverse; logging opcional
                logger.warning(f"Erro ao configurar campo blur {campo.nome_campo}: {str(e)}")
                pass

        if campo.funcao_tratamento:
            attrs['data-funcao-tratamento'] = campo.funcao_tratamento

        return attrs


    def _parse_select_options(self, entrada_espec):
        if not entrada_espec:
            return []

        # Se já for um dicionário (caso raro)
        if isinstance(entrada_espec, dict):
            return [(str(k), str(v)) for k, v in entrada_espec.items()]

        # Se for string, tenta como JSON ou lista de tuplas
        if isinstance(entrada_espec, str):
            try:
                # Tenta como JSON (formato preferido)
                try:
                    opcoes_dict = json.loads(entrada_espec.strip())
                    if isinstance(opcoes_dict, dict):
                        return [(str(k), str(v)) for k, v in opcoes_dict.items()]
                except json.JSONDecodeError:
                    # Se falhar, tenta como lista de tuplas (para compatibilidade)
                    if entrada_espec.strip().startswith('[') and '),' in entrada_espec:
                        lista_tuplas = ast.literal_eval(entrada_espec.strip().replace(')(', '),('))
                        return [(str(k), str(v)) for k, v in lista_tuplas]
            except Exception as e:
                logger.error(f"Erro ao processar entrada_espec: {entrada_espec}. Erro: {str(e)}")

        return [('erro', 'Formato inválido')]
    

    def _resolve_value_and_label_fields(self, model_ref, campo=None):
        if campo and campo.tabela_referencia:
            config = validate_reference_config(parse_reference(campo), model_ref=model_ref)
            return config['campo_chave'], config['campo_display']
        return model_ref._meta.pk.name, model_ref._meta.pk.name

    def _resolve_dependencias(self, mapeamento_dependencias, dependencias=None):
        """Resolve o mapeamento de dependências usando os valores da tela e do form atual."""
        dependencias = dict(dependencias or {})

        if self.initial:
            for campo_local, valor in self.initial.items():
                if campo_local not in dependencias:
                    dependencias[campo_local] = valor

        resolvidos = {}
        for campo_tabela_ref, campo_local in mapeamento_dependencias.items():
            if not campo_tabela_ref or not campo_local:
                continue

            valor_dependencia = None
            campo_local_normalizado = normalize_reference_name(campo_local)
            for chave, valor in dependencias.items():
                if chave is None:
                    continue
                if normalize_reference_name(chave) == campo_local_normalizado:
                    valor_dependencia = valor
                    break

            if valor_dependencia in (None, '', [], {}):
                continue

            resolvidos[campo_tabela_ref] = valor_dependencia

        return resolvidos

    def _get_referencia_options(self, json_data, dependencias=None, campo=None):
        """Obtém opções de referência para campos select usando o DSL oficial do projeto.

        A resolução é totalmente genérica: o identificador de tabela e o mapeamento de
        dependências são lidos do metadado e aplicados no momento da consulta.
        """
        if json_data is None:
            return []

        valor = str(json_data).strip()
        if not valor:
            return []

        try:
            config = parse_reference(campo or valor)
            model_ref = resolve_reference_model(config)
            config = validate_reference_config(config, model_ref=model_ref)
            form_values = dependencias or self.initial
            dependency_values = {
                local_name: next(
                    (value for key, value in form_values.items()
                     if normalize_reference_name(key) == normalize_reference_name(local_name)),
                    None,
                )
                for local_name in config['filtros'].values()
            }
            return [
                (str(key), str(display) if display is not None else str(key))
                for key, display in get_reference_options(
                    config,
                    filtros=dependency_values if config['filtros'] else None,
                )
                if key is not None
            ]

        except ValueError as exc:
            logger.warning("tabela_referencia rejeitada em _get_referencia_options: %s. %s", valor, exc)
            return []
        except Exception as e:
            logger.error(f"Erro ao processar referencia_options com tabela_referencia: {valor}. Erro: {str(e)}", exc_info=True)
            return []

    def _handle_select_field(self, campo, attrs):
        try:
            # REGRA: Se o campo é varchar5 (CPF/CNPJ), NÃO criar Select mesmo tendo FK
            # Esses campos precisam ser digitáveis com máscara
            if campo.tipo_campo.lower() == 'varchar5':
                return None  # Retorna None para cair no fluxo normal de TextInput

            if campo.entrada_espec:
                field = forms.ChoiceField(
                    label=campo.label_campo,
                    choices=self._parse_select_options(campo.entrada_espec),
                    required=campo.obrigatorio,
                    initial=self.initial.get(campo.nome_campo),
                    widget=forms.Select(attrs=attrs)
                )
                field.tabela_referencia = None
                return field
            elif campo.tabela_referencia:
                field = forms.ChoiceField(
                    label=campo.label_campo,
                    choices=self._get_referencia_options(campo.tabela_referencia, dependencias=self.initial, campo=campo),
                    required=campo.obrigatorio,
                    initial=self.initial.get(campo.nome_campo),
                    widget=forms.Select(attrs=attrs)
                )
                field.tabela_referencia = campo.tabela_referencia
                field.campo = campo
                return field
        except Exception as e:
            logger.error(f"Erro ao criar select: {str(e)}")
        return None

    def _create_field_by_type(self, campo, attrs):
        initial = self.initial.get(campo.nome_campo)
        tipo = campo.tipo_campo.lower()

        if tipo == 'varchar5':
            attrs['maxlength'] = 18  # Garantia extra no HTML
            return forms.CharField(
                label=campo.label_campo,
                max_length=18,
                required=campo.obrigatorio,
                initial=initial,
                validators=[
                    RegexValidator(
                        r'^(\d{11}|\d{14}|\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})$',
                        'Formato inválido para CPF (000.000.000-00) ou CNPJ (00.000.000/0000-00)'
                    )
                ],
                widget=forms.TextInput(attrs=attrs)
            )

        elif tipo in ['varchar', 'char']:
            attrs['maxlength'] = campo.tamanho  # Limita tamanho no front-end
            return forms.CharField(
                label=campo.label_campo,
                max_length=campo.tamanho,
                required=campo.obrigatorio,
                initial=initial,
                widget=forms.TextInput(attrs=attrs)
            )  

        elif tipo in ['integer', 'int']:
            attrs['maxlength'] = campo.tamanho  # Limita número de dígitos no input
            max_value = int('9' * campo.tamanho) if campo.tamanho else None  # Ex: tamanho 3 → 999

            return forms.IntegerField(
                label=campo.label_campo,
                required=campo.obrigatorio,
                initial=initial,
                min_value=0,  # Evita negativos, ajuste se necessário
                max_value=max_value,
                widget=forms.NumberInput(attrs=attrs)
            )

        elif tipo in ['float', 'numeric']:
            # Calcula max_digits baseado no tamanho total e casas decimais
            total_digits = campo.tamanho or 20  # Fallback se não definido
            decimal_places = campo.decimais or 2
            max_digits = total_digits + decimal_places

            attrs['maxlength'] = max_digits + 1  # +1 para ponto decimal
             
            return forms.DecimalField(
                label=campo.label_campo,
                max_digits=max_digits,
                decimal_places=decimal_places,
                required=campo.obrigatorio,
                initial=initial,
                widget=forms.NumberInput(attrs=attrs)
            )

        elif tipo == 'date':
            attrs.update({'type': 'date'})
            return forms.DateField(
                label=campo.label_campo,
                required=campo.obrigatorio,
                initial=initial,
                widget=forms.DateInput(attrs=attrs)
            )

        elif tipo == 'boolean':
            return forms.BooleanField(
                label=campo.label_campo,
                required=False,
                initial=initial,
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
            )

        elif tipo == 'disable':
            attrs['readonly'] = 'readonly'
            attrs['aria-readonly'] = 'true'
            attrs['data-disable-field'] = 'true'
            attrs['class'] = attrs.get('class', '') + ' campo-disable'
            attrs['style'] = (
                (attrs.get('style', '') + '; ') if attrs.get('style') else ''
            ) + 'background-color: #e9ecef; cursor: not-allowed;'
            return forms.CharField(
                label=campo.label_campo,
                required=False,
                initial=initial,
                widget=forms.TextInput(attrs=attrs)
            )

        else:
            return forms.CharField(
                label=campo.label_campo,
                required=campo.obrigatorio,
                initial=initial,
                widget=forms.TextInput(attrs=attrs)
            )

    def generate_form_class(self):
        campos = {}
        for field_name, campo in self.estrutura_campos.items():
            try:
                attrs = self._get_field_attrs(campo)
                
                # Adiciona classe à linha do formulário se for um campo chave
                extra_css = ' campo-chave-row' if campo.ordem_campo <= self.max_ordem_blur else ''
                
                select_field = self._handle_select_field(campo, attrs)
                if select_field:
                    select_field.widget.attrs['class'] += extra_css
                    campos[field_name] = select_field
                else:
                    field = self._create_field_by_type(campo, attrs)
                    field.widget.attrs['class'] += extra_css
                    campos[field_name] = field
            except Exception as e:
                logger.error(f"Erro ao processar campo {field_name}: {str(e)}")

        # Cria a classe DynamicForm
        DynamicForm = type('DynamicForm', (forms.Form,), campos)
        generator_ref = self

        def _get_referencia_options_for_form(form_instance, tabela_referencia, dependencias=None, campo=None):
            return generator_ref._get_referencia_options(tabela_referencia, dependencias=dependencias, campo=campo)

        DynamicForm._get_referencia_options = staticmethod(_get_referencia_options_for_form)

        def __init__(self, *args, **kwargs):
            super(DynamicForm, self).__init__(*args, **kwargs)
            for nome_campo, field in self.fields.items():
                tabela_referencia = getattr(field, 'tabela_referencia', None)
                if not tabela_referencia:
                    continue

                dependencias = {}
                if self.initial:
                    dependencias.update(self.initial)
                if self.data:
                    dependencias.update({key: value for key, value in self.data.items() if value not in (None, '')})

                field.choices = DynamicForm._get_referencia_options(
                    self,
                    tabela_referencia,
                    dependencias=dependencias,
                    campo=getattr(field, 'campo', None),
                )

        # Injeta o método clean para remover máscara de CPF/CNPJ antes de validar
        def clean(self):
            cleaned_data = super(DynamicForm, self).clean()
            for nome, valor in cleaned_data.items():
                campo_meta = self.fields[nome]
                if hasattr(campo_meta, 'widget') and campo_meta.widget.attrs.get('data-mask-cpfcnpj') == 'true':
                    if isinstance(valor, str):
                        cleaned_data[nome] = re.sub(r'\D', '', valor)
            return cleaned_data

        DynamicForm.__init__ = __init__
        DynamicForm.clean = clean

        return DynamicForm


def generate_dynamic_form(tabela, initial=None):
    generator = DynamicFormGenerator(tabela, initial)
    return generator.generate_form_class()
