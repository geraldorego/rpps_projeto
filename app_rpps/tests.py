import json

from django.test import TestCase, RequestFactory, SimpleTestCase
from .metadata_helpers import (
    normalize_chave_tipo,
    is_primary_key_field,
    is_foreign_key_field,
    is_composite_foreign_key_field,
    safe_model_filter,
)
from .models import RPPS
from .services.referencia_service import (
    find_reference_record,
    get_reference_options,
    normalize_reference_key,
    parse_reference,
    resolve_reference_model,
    resolve_reference_display,
    validate_reference_config,
)
from .utils import format_referencia_html
from .forms import DynamicFormGenerator
from unittest.mock import Mock, patch
from django.db import IntegrityError
from types import SimpleNamespace


class TestReferenceServiceParsing(SimpleTestCase):
    """Testes puros do contrato normalizado de referência, sem banco de dados."""

    def test_simple_reference_separates_key_local_field_and_display(self):
        structure = type('Structure', (), {
            'tabela_referencia': 'Cadastro(CpfCnpj=CPF)',
            'referencia_config': None,
            'campo_display_referencia': 'Nome',
        })()
        config = parse_reference(structure)
        self.assertEqual(config['tabela'], 'Cadastro')
        self.assertEqual(config['campo_chave'], 'CpfCnpj')
        self.assertEqual(config['campo_local'], 'CPF')
        self.assertEqual(config['campo_display'], 'Nome')
        self.assertEqual(config['filtros'], {})

    def test_composite_reference_keeps_first_pair_and_all_dependencies(self):
        config = parse_reference(
            'GruposColegiados(ano_ref=ano_ref,mes_ref=mes_ref,TipoFundo=TipoFundo)'
        )
        self.assertIsNone(config['campo_chave'])
        self.assertEqual(config['filtros'], {
            'ano_ref': 'ano_ref',
            'mes_ref': 'mes_ref',
            'TipoFundo': 'TipoFundo',
        })

    def test_reference_options_endpoint_loads_and_refreshes_all_dependencies(self):
        from . import views

        structure = SimpleNamespace(
            tabela_referencia=(
                'GruposColegiados(Codigo=CodigoGrupoColegiado,ano_ref=ano_ref,'
                'mes_ref=mes_ref,TipoFundo=TipoFundo)'
            ),
            referencia_config=None,
            campo_display_referencia=None,
        )
        metadata_query = Mock()
        metadata_query.first.return_value = structure
        response_by_filter = {
            (2026, 7, 1): [(10, 10), (11, 11)],
            (2026, 6, 1): [(12, 12)],
            (2026, 7, 2): [(13, 13)],
        }

        def options_side_effect(config, filtros=None, search_term=None):
            key = (int(filtros['ano_ref']), int(filtros['mes_ref']), int(filtros['TipoFundo']))
            return response_by_filter[key]

        responses = []
        with patch('app_rpps.views.RppsEstrutura.objects.filter', return_value=metadata_query), \
                patch('app_rpps.views.resolve_reference_model', return_value=__import__(
                    'app_rpps.models', fromlist=['GruposColegiados']).GruposColegiados), \
                patch('app_rpps.views.validate_reference_config', side_effect=lambda config, model_ref=None: {
                    **config, 'modelo': model_ref,
                }), \
                patch('app_rpps.views.get_reference_options', side_effect=options_side_effect) as get_options:
            for mes_ref, tipo_fundo in ((7, 1), (6, 1), (7, 2)):
                request = RequestFactory().get('/api/reference-options/MembroColegio/CodigoGrupoColegiado/', {
                    'ano_ref': 2026,
                    'mes_ref': mes_ref,
                    'TipoFundo': tipo_fundo,
                })
                request.user = SimpleNamespace(is_authenticated=True)
                responses.append(views.reference_options(request, 'MembroColegio', 'CodigoGrupoColegiado'))

        response_data = [json.loads(item.content) for item in responses]
        self.assertEqual([item['value'] for item in response_data[0]['results']], ['10', '11'])
        self.assertEqual([item['value'] for item in response_data[1]['results']], ['12'])
        self.assertEqual([item['value'] for item in response_data[2]['results']], ['13'])
        self.assertEqual(get_options.call_args_list[0].kwargs['filtros'], {
            'ano_ref': '2026', 'mes_ref': '7', 'TipoFundo': '1',
        })

    def test_reference_options_endpoint_waits_until_all_dependencies_are_present(self):
        from . import views

        structure = SimpleNamespace(
            tabela_referencia=(
                'GruposColegiados(Codigo=CodigoGrupoColegiado,ano_ref=ano_ref,'
                'mes_ref=mes_ref,TipoFundo=TipoFundo)'
            ),
            referencia_config=None,
            campo_display_referencia=None,
        )
        metadata_query = Mock()
        metadata_query.first.return_value = structure
        from .models import GruposColegiados

        request = RequestFactory().get('/api/reference-options/MembroColegio/CodigoGrupoColegiado/', {
            'ano_ref': 2026,
            'mes_ref': '',
            'TipoFundo': 1,
        })
        request.user = SimpleNamespace(is_authenticated=True)
        with patch('app_rpps.views.RppsEstrutura.objects.filter', return_value=metadata_query), \
                patch('app_rpps.views.resolve_reference_model', return_value=GruposColegiados), \
                patch('app_rpps.views.validate_reference_config', side_effect=lambda config, model_ref=None: {
                    **config, 'modelo': model_ref,
                }), \
                patch('app_rpps.views.get_reference_options') as get_options:
            response = views.reference_options(request, 'MembroColegio', 'CodigoGrupoColegiado')

        self.assertEqual(json.loads(response.content), {'ready': False, 'missing': ['mes_ref'], 'results': []})
        get_options.assert_not_called()

    def test_reference_options_endpoint_preserves_simple_cpf_reference(self):
        from . import views
        from .models import Cadastro

        structure = SimpleNamespace(
            tabela_referencia='Cadastro(CpfCnpj=CPF)',
            referencia_config=None,
            campo_display_referencia='Nome',
        )
        metadata_query = Mock()
        metadata_query.first.return_value = structure
        request = RequestFactory().get('/api/reference-options/MembroColegio/CPF/')
        request.user = SimpleNamespace(is_authenticated=True)
        with patch('app_rpps.views.RppsEstrutura.objects.filter', return_value=metadata_query), \
                patch('app_rpps.views.resolve_reference_model', return_value=Cadastro), \
                patch('app_rpps.views.validate_reference_config', side_effect=lambda config, model_ref=None: {
                    **config, 'modelo': model_ref,
                }), \
                patch('app_rpps.views.get_reference_options', return_value=[('12345678900', 'Cadastro de teste')]) as get_options:
            response = views.reference_options(request, 'MembroColegio', 'CPF')

        self.assertEqual(json.loads(response.content)['results'], [{'value': '12345678900', 'text': 'Cadastro de teste'}])
        get_options.assert_called_once_with(
            get_options.call_args.args[0], filtros={},
        )

    def test_reference_options_keep_key_separate_and_apply_every_filter(self):
        from unittest.mock import Mock

        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.values_list.return_value = queryset
        queryset.order_by.return_value = [('001', 'Nome relacionado')]
        model_ref = Mock()
        model_ref.objects.all.return_value = queryset
        config = {
            'tabela': 'FakeReference',
            'campo_chave': 'Codigo',
            'campo_local': None,
            'campo_display': 'Nome',
            'filtros': {'ano_ref': 'ano_ref', 'mes_ref': 'mesref', 'TipoFundo': 'TipoFundo'},
            'modelo': model_ref,
        }
        with patch('app_rpps.services.referencia_service.validate_reference_config', return_value=config), \
                patch('app_rpps.services.referencia_service.safe_model_filter', side_effect=lambda model, filters: filters):
            result = list(get_reference_options(config, filtros={
                'ano_ref': 2024,
                'mesref': 7,
                'TipoFundo': 2,
            }))
        self.assertEqual(result, [('001', 'Nome relacionado')])
        queryset.filter.assert_called_once_with(ano_ref=2024, mes_ref=7, TipoFundo=2)

    def test_reference_display_prefers_description_without_changing_key(self):
        queryset = Mock()
        queryset.values_list.return_value = queryset
        queryset.order_by.return_value = [(2, 'Conselho Fiscal')]

        class FakeField:
            many_to_many = False
            many_to_one = False
            one_to_many = False

        class FakeMeta:
            pk = type('PrimaryKey', (), {'name': 'id'})()
            fields = [type('NamedField', (), {'name': name})() for name in ('id', 'Codigo', 'Descricao')]

            @staticmethod
            def get_field(name):
                if name not in {'id', 'Codigo', 'Descricao'}:
                    raise LookupError(name)
                return FakeField()

        class FakeModel:
            _meta = FakeMeta()
            objects = Mock()

        FakeModel.objects.all.return_value = queryset

        config = {
            'tabela': 'FakeReference',
            'campo_chave': 'Codigo',
            'campo_local': 'CodigoGrupoColegiado',
            'campo_display': 'Codigo',
            'filtros': {},
        }
        validated = validate_reference_config(config, model_ref=FakeModel)
        self.assertEqual(validated['campo_chave'], 'Codigo')
        self.assertEqual(validated['campo_display'], 'Descricao')
        with patch('app_rpps.services.referencia_service.resolve_reference_model', return_value=FakeModel), \
                patch('app_rpps.services.referencia_service.safe_model_filter', return_value={}):
            options = list(get_reference_options(config))
        self.assertEqual(options, [(2, 'Conselho Fiscal')])
        queryset.values_list.assert_called_once_with('Codigo', 'Descricao')

    def test_invalid_description_name_uses_non_filter_enum_metadata(self):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.values_list.return_value = queryset
        queryset.order_by.return_value = [(1, 1), (2, 2)]

        class FakeField:
            many_to_many = False
            many_to_one = False
            one_to_many = False

            def __init__(self, field_type):
                self.field_type = field_type

            def get_internal_type(self):
                return self.field_type

        class FakeMeta:
            db_table = 'GruposColegiados'
            verbose_name = 'Grupos Colegiados'
            verbose_name_plural = 'Grupos Colegiados'
            pk = type('PrimaryKey', (), {'name': 'id'})()
            fields = [type('NamedField', (), {'name': name})() for name in (
                'id', 'Codigo', 'ano_ref', 'mes_ref', 'TipoFundo', 'Tipo', 'TipoAto', 'VeiculoPublicacao',
            )]

            @staticmethod
            def get_field(name):
                types = {'Tipo': 'IntegerField', 'TipoAto': 'IntegerField', 'VeiculoPublicacao': 'IntegerField'}
                if name not in {'id', 'Codigo', 'ano_ref', 'mes_ref', 'TipoFundo', 'Tipo', 'TipoAto', 'VeiculoPublicacao'}:
                    raise LookupError(name)
                return FakeField(types.get(name, 'IntegerField'))

        class FakeModel:
            _meta = FakeMeta()
            objects = Mock()

        FakeModel.objects.all.return_value = queryset
        config = {
            'tabela': 'GruposColegiados',
            'campo_chave': 'Codigo',
            'campo_local': 'CodigoGrupoColegiado',
            'campo_display': 'Descricao',
            'filtros': {'ano_ref': 'ano_ref', 'mes_ref': 'mes_ref', 'TipoFundo': 'TipoFundo'},
        }
        reference_fields = [
            {'nome_campo': 'TipoFundo', 'label_campo': 'Fundo', 'entrada_espec': '{"1":"Previdenciário"}'},
            {'nome_campo': 'Tipo', 'label_campo': 'Tipo do Grupo Colegiado',
             'entrada_espec': '{"1":"Conselho Deliberativo","2":"Conselho Fiscal"}'},
              {'nome_campo': 'TipoAto', 'label_campo': 'Tipo do Ato Constitutivo',
               'entrada_espec': '{"1":"Lei","2":"Decreto"}'},
              {'nome_campo': 'VeiculoPublicacao', 'label_campo': 'Publicação do Ato de Criação',
               'entrada_espec': '{"1":"Diário Oficial"}'},
        ]
        with patch('app_rpps.services.referencia_service.resolve_reference_model', return_value=FakeModel), \
                patch('app_rpps.services.referencia_service._get_reference_structure_fields', return_value=reference_fields), \
                patch('app_rpps.services.referencia_service.safe_model_filter', side_effect=lambda model, filters: filters):
            options = list(get_reference_options(config, filtros={
                'ano_ref': 2026, 'mes_ref': 7, 'TipoFundo': 1,
            }))

        self.assertEqual(options, [(1, 'Conselho Deliberativo'), (2, 'Conselho Fiscal')])
        queryset.filter.assert_called_once_with(ano_ref=2026, mes_ref=7, TipoFundo=1)
        queryset.values_list.assert_called_once_with('Codigo', 'Tipo')

    def test_dynamic_form_options_preserve_key_as_value(self):
        generator = DynamicFormGenerator.__new__(DynamicFormGenerator)
        generator.initial = {}
        structure = type('Structure', (), {
            'tabela_referencia': 'Cadastro(CpfCnpj=CPF)',
            'referencia_config': None,
            'campo_display_referencia': 'Nome',
        })()
        config = {
            'tabela': 'Cadastro', 'campo_chave': 'CpfCnpj', 'campo_local': 'CPF',
            'campo_display': 'Nome', 'filtros': {},
        }
        with patch('app_rpps.forms.resolve_reference_model', return_value=object()), \
                patch('app_rpps.forms.validate_reference_config', return_value=config), \
                patch('app_rpps.forms.get_reference_options', return_value=[('12345678900', 'João da Silva')]):
            choices = generator._get_referencia_options('Cadastro(CpfCnpj=CPF)', campo=structure)
        self.assertEqual(choices, [('12345678900', 'João da Silva')])

    def test_reference_html_escapes_values(self):
        html = format_referencia_html(
            [{'id': 1, 'descricao': '<script>alert(1)</script>'}],
            {'tipo_display': 'label', 'campos_retorno': ['id', 'descricao']},
        )
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_missing_reference_returns_none_without_creation(self):
        model_ref = Mock()
        model_ref.objects.filter.return_value.first.return_value = None
        config = {
            'tabela': 'Cadastro', 'campo_chave': 'CpfCnpj', 'campo_local': 'CPF',
            'campo_display': 'Nome', 'filtros': {}, 'modelo': model_ref,
        }
        with patch('app_rpps.services.referencia_service.validate_reference_config', return_value=config):
            _, record = find_reference_record(config, '12345678900')
        self.assertIsNone(record)
        model_ref.objects.filter.assert_called_once_with(CpfCnpj='12345678900')
        model_ref.objects.create.assert_not_called()

    def test_existing_reference_uses_configured_key_and_returns_display(self):
        record = type('RelatedRecord', (), {'CpfCnpj': '12345678900', 'Nome': 'João da Silva'})()
        model_ref = Mock()
        model_ref.objects.filter.return_value.first.return_value = record
        config = {
            'tabela': 'Cadastro', 'campo_chave': 'CpfCnpj', 'campo_local': 'CPF',
            'campo_display': 'Nome', 'filtros': {}, 'modelo': model_ref,
        }
        with patch('app_rpps.services.referencia_service.validate_reference_config', return_value=config):
            _, found = find_reference_record(config, '12345678900')
            display = resolve_reference_display(config, found)
        model_ref.objects.filter.assert_called_once_with(CpfCnpj='12345678900')
        self.assertEqual(found.CpfCnpj, '12345678900')
        self.assertEqual(display, 'João da Silva')

    def test_document_key_normalization_accepts_masked_and_unmasked_values(self):
        self.assertEqual(normalize_reference_key('123.456.789-00', document=True), '12345678900')
        self.assertEqual(normalize_reference_key('12345678900', document=True), '12345678900')

    def test_dynamic_document_field_accepts_masked_and_unmasked_values(self):
        generator = DynamicFormGenerator.__new__(DynamicFormGenerator)
        generator.initial = {}
        field = generator._create_field_by_type(type('StructureField', (), {
            'nome_campo': 'CPF', 'tipo_campo': 'varchar5', 'tamanho': 18,
            'label_campo': 'CPF', 'obrigatorio': False,
        })(), {})
        self.assertEqual(field.clean('12345678900'), '12345678900')
        self.assertEqual(field.clean('123.456.789-00'), '123.456.789-00')

    def test_reference_validation_accepts_id_and_non_id_keys(self):
        class FakeField:
            many_to_many = False
            many_to_one = False
            one_to_many = False

        class FakeMeta:
            app_label = 'app_rpps'
            db_table = 'FakeReference'
            pk = type('PrimaryKey', (), {'name': 'id'})()
            fields = [type('NamedField', (), {'name': name})() for name in ('id', 'CpfCnpj', 'Nome')]

            @staticmethod
            def get_field(name):
                if name not in {'id', 'CpfCnpj', 'Nome'}:
                    raise LookupError(name)
                return FakeField()

        class FakeModel:
            __name__ = 'FakeReference'
            _meta = FakeMeta()

        for key_field in ('id', 'CpfCnpj'):
            config = {
                'tabela': 'FakeReference', 'campo_chave': key_field,
                'campo_local': None, 'campo_display': 'Nome', 'filtros': {},
            }
            validated = validate_reference_config(config, model_ref=FakeModel)
            self.assertEqual(validated['campo_chave'], key_field)

    def test_invalid_key_fails_and_invalid_display_uses_valid_fallback(self):
        class FakeMeta:
            pk = type('PrimaryKey', (), {'name': 'id'})()
            fields = [type('NamedField', (), {'name': name})() for name in ('id', 'Nome')]

            @staticmethod
            def get_field(name):
                if name not in {'id', 'Nome'}:
                    raise LookupError(name)
                return type('FakeField', (), {'many_to_many': False, 'many_to_one': False, 'one_to_many': False})()

        class FakeModel:
            _meta = FakeMeta()

        invalid_key = {'tabela': 'Fake', 'campo_chave': 'missing', 'campo_display': 'Nome', 'filtros': {}}
        with self.assertRaises(ValueError):
            validate_reference_config(invalid_key, model_ref=FakeModel)

        invalid_display = {'tabela': 'Fake', 'campo_chave': 'id', 'campo_display': 'missing', 'filtros': {}}
        validated = validate_reference_config(invalid_display, model_ref=FakeModel)
        self.assertEqual(validated['campo_display'], 'Nome')


class TestPeriodCopyService(SimpleTestCase):
    def _period_model_and_metadata(self):
        class FakeField:
            many_to_many = False
            many_to_one = False
            one_to_many = False

            @staticmethod
            def to_python(value):
                return value

        class FakeMeta:
            db_table = 'GenericPeriodRecord'

            @staticmethod
            def get_field(name):
                if name not in {'ano_ref', 'mes_ref'}:
                    raise LookupError(name)
                return FakeField()

        class FakeModel:
            __name__ = 'GenericPeriodRecord'
            _meta = FakeMeta()

        metadata = [
            SimpleNamespace(nome_campo='ano_ref', tipo_campo='int', tamanho=4, label_campo='Ano'),
            SimpleNamespace(nome_campo='mes_ref', tipo_campo='int', tamanho=2, label_campo='Mês'),
        ]
        return FakeModel, metadata

    def test_period_field_specs_accept_name_type_and_size(self):
        from .services.copy_service import normalize_period_field_specs

        self.assertEqual(
            normalize_period_field_specs([['ano_ref', 'int', 4], ['mes_ref', 'INT', 2], 'legado']),
            [
                {'name': 'ano_ref', 'type': 'int', 'size': 4},
                {'name': 'mes_ref', 'type': 'int', 'size': 2},
                {'name': 'legado', 'type': None, 'size': None},
            ],
        )
        for invalid in ([['ano_ref', 'int', 0]], [['ano_ref', 'int', '4']], [[1, 'int', 4]], [['a', 'b', 3, 4]]):
            with self.assertRaises(ValueError):
                normalize_period_field_specs(invalid)

    def test_period_fields_must_exist_in_rppsestrutura(self):
        from .services.copy_service import validate_period_fields_metadata

        model, metadata = self._period_model_and_metadata()
        with patch('app_rpps.services.copy_service.RppsEstrutura.objects.filter', return_value=metadata[:1]):
            with self.assertRaisesRegex(ValueError, 'mes_ref'):
                validate_period_fields_metadata(
                    model, 'Generic', {'campos_periodo': [['ano_ref', 'int', 4], ['mes_ref', 'int', 2]]}
                )

    def test_divergent_type_and_size_warn_and_prefer_crud_c_configuration(self):
        from .services.copy_service import validate_period_fields_metadata

        model, metadata = self._period_model_and_metadata()
        with patch('app_rpps.services.copy_service.RppsEstrutura.objects.filter', return_value=metadata), \
                self.assertLogs('app_rpps.services.copy_service', level='WARNING') as logs:
            fields = validate_period_fields_metadata(
                model, 'Generic', {'campos_periodo': [['ano_ref', 'int', 6], ['mes_ref', 'varchar', 2]]}
            )
        self.assertEqual(len(logs.records), 2)
        self.assertEqual((fields[0]['type'], fields[0]['size']), ('int', 6))
        self.assertEqual((fields[1]['type'], fields[1]['size']), ('varchar', 2))
        self.assertEqual(fields[0]['label'], 'Ano')

    def test_period_size_is_digit_count_and_enforced_on_backend(self):
        from .services.copy_service import _normalize_period_values

        model, _ = self._period_model_and_metadata()
        specs = [
            {'name': 'ano_ref', 'type': 'int', 'size': 4, 'label': 'Ano'},
            {'name': 'mes_ref', 'type': 'int', 'size': 2, 'label': 'Mês'},
        ]

        self.assertEqual(
            _normalize_period_values(model, specs, {'ano_ref': '2026', 'mes_ref': '12'}),
            {'ano_ref': '2026', 'mes_ref': '12'},
        )
        # 99999 é um número grande, mas o limite é de dígitos: '0007' (4 dígitos) é válido.
        self.assertEqual(_normalize_period_values(model, specs, {'ano_ref': '0007', 'mes_ref': '07'})['mes_ref'], '07')
        for invalid in (
            {'ano_ref': '202612', 'mes_ref': '12'},
            {'ano_ref': '2026', 'mes_ref': '123'},
            {'ano_ref': '20a6', 'mes_ref': '12'},
            {'ano_ref': '2026', 'mes_ref': '-1'},
            {'ano_ref': '2026', 'mes_ref': '1.5'},
        ):
            with self.assertRaises(ValueError):
                _normalize_period_values(model, specs, invalid)

    def test_matching_configuration_does_not_warn(self):
        from .services.copy_service import validate_period_fields_metadata

        model, metadata = self._period_model_and_metadata()
        with patch('app_rpps.services.copy_service.RppsEstrutura.objects.filter', return_value=metadata), \
                self.assertNoLogs('app_rpps.services.copy_service', level='WARNING'):
            validate_period_fields_metadata(
                model, 'Generic', {'campos_periodo': [['ano_ref', 'int', 4], ['mes_ref', 'int', 2]]}
            )

    def test_copy_action_parameters_require_period_fields(self):
        from .services.copy_service import parse_copy_action_parameters

        self.assertEqual(parse_copy_action_parameters({
            'tipo': 'periodo',
            'campos_periodo': ['ano_ref', 'mes_ref'],
            'confirmar': True,
            'ignorar_existentes': True,
        })['campos_periodo'], ['ano_ref', 'mes_ref'])
        with self.assertRaises(ValueError):
            parse_copy_action_parameters({'tipo': 'periodo', 'campos_periodo': []})

    def test_copy_preserves_values_and_skips_existing_composite_key(self):
        from contextlib import nullcontext
        from .services.copy_service import copy_period_records, preview_period_copy

        class FakeField:
            many_to_many = False
            many_to_one = False
            one_to_many = False

            def __init__(self, name, primary_key=False, auto_created=False, integer=False):
                self.name = name
                self.primary_key = primary_key
                self.auto_created = auto_created
                self.integer = integer

            def to_python(self, value):
                return int(value) if self.integer else value

            def get_internal_type(self):
                return 'AutoField' if self.name == 'id' else 'IntegerField' if self.integer else 'CharField'

        fields = [
            FakeField('id', primary_key=True, auto_created=False, integer=True),
            FakeField('ano_ref', integer=True),
            FakeField('mes_ref', integer=True),
            FakeField('Codigo', integer=True),
            FakeField('Descricao'),
        ]

        class FakeMeta:
            app_label = 'app_rpps'
            db_table = 'GenericPeriodRecord'
            pk = fields[0]
            concrete_fields = fields
            unique_together = (('ano_ref', 'mes_ref', 'Codigo'),)
            constraints = ()

            @staticmethod
            def get_field(name):
                return next(field for field in fields if field.name == name)

        class QuerySet(list):
            def count(self):
                return len(self)

            def exists(self):
                return bool(self)

        class Manager:
            def __init__(self, records):
                self.records = records

            def filter(self, **criteria):
                return QuerySet(
                    record for record in self.records
                    if all(getattr(record, name) == value for name, value in criteria.items())
                )

            def create(self, **values):
                values['id'] = max((record.id for record in self.records), default=0) + 1
                record = SimpleNamespace(**values)
                self.records.append(record)
                return record

        class FakeModel:
            __name__ = 'GenericPeriodRecord'
            _meta = FakeMeta()

        FakeModel.objects = Manager([
            SimpleNamespace(id=1, ano_ref=2024, mes_ref=1, Codigo=10, Descricao='Registro dez'),
            SimpleNamespace(id=2, ano_ref=2024, mes_ref=1, Codigo=11, Descricao='Registro onze'),
            SimpleNamespace(id=3, ano_ref=2025, mes_ref=2, Codigo=10, Descricao='Já existe'),
        ])
        key_metadata = SimpleNamespace(
            campo_chave_blur="('ano_ref', 'mes_ref', 'Codigo')",
            tipo_chave_blur='unique',
            nome_campo='Codigo',
            tipo_campo='int', tamanho=4, label_campo='Código',
        )
        period_metadata = [
            SimpleNamespace(nome_campo='ano_ref', tipo_campo='int', tamanho=4, label_campo='Ano',
                            tipo_chave_blur='', campo_chave_blur=''),
            SimpleNamespace(nome_campo='mes_ref', tipo_campo='int', tamanho=2, label_campo='Mês',
                            tipo_chave_blur='', campo_chave_blur=''),
        ]
        parameters = {
            'tipo': 'periodo',
            'campos_periodo': [['ano_ref', 'int', 4], ['mes_ref', 'int', 2]],
            'confirmar': True,
            'ignorar_existentes': True,
        }

        with patch('app_rpps.services.copy_service.RppsEstrutura.objects.filter', return_value=[key_metadata, *period_metadata]), \
                patch('app_rpps.services.copy_service.transaction.atomic', side_effect=lambda: nullcontext()):
            preview = preview_period_copy(
                FakeModel,
                'GenericPeriodRecord',
                parameters,
                {'ano_ref': '2024', 'mes_ref': '1'},
                {'ano_ref': '2025', 'mes_ref': '2'},
            )
            self.assertEqual(preview['found'], 2)
            self.assertEqual(len(FakeModel.objects.records), 3)
            result = copy_period_records(
                FakeModel,
                'GenericPeriodRecord',
                parameters,
                {'ano_ref': '2024', 'mes_ref': '1'},
                {'ano_ref': '2025', 'mes_ref': '2'},
            )

        self.assertEqual(result['found'], 2)
        self.assertEqual(result['copied'], 1)
        self.assertEqual(result['ignored'], 1)
        self.assertEqual(result['errors'], 0)
        copied = next(record for record in FakeModel.objects.records if record.Codigo == 11 and record.ano_ref == 2025)
        self.assertEqual(copied.mes_ref, 2)
        self.assertEqual(copied.Descricao, 'Registro onze')


class TestPeriodCopyEndpoint(SimpleTestCase):
    def _request(self, phase, confirmed=None):
        from django.test import RequestFactory

        payload = {
            'fase': phase,
            'origem_ano_ref': '2026',
            'origem_mes_ref': '8',
            'destino_ano_ref': '2026',
            'destino_mes_ref': '9',
        }
        if confirmed is not None:
            payload['confirmado'] = confirmed
        request = RequestFactory().post('/tratamento/Generic/copiar/', payload)
        request.user = SimpleNamespace(is_authenticated=True, has_perm=lambda permission: True)
        return request

    def test_preview_does_not_write_and_execute_requires_confirmation(self):
        from . import views

        menu_item = SimpleNamespace(
            acao='CRUD-C',
            parametros_acao='{"tipo":"periodo","campos_periodo":["ano_ref","mes_ref"],"confirmar":true,"ignorar_existentes":true}',
            requer_permissao=False,
            aplicativo='app_rpps',
            arquivo='GenericPeriodRecord',
        )
        with patch('app_rpps.views.get_object_or_404', return_value=menu_item), \
                patch('app_rpps.views.apps.get_model', return_value=object), \
                patch('app_rpps.views.preview_period_copy', return_value={'found': 4}) as preview, \
                patch('app_rpps.views.copy_period_records', return_value={
                    'found': 4, 'copied': 3, 'ignored': 1, 'errors': 0, 'error_messages': [],
                }) as copy:
            preview_response = views.copy_period_records_view(self._request('preview'), 'Generic')
            self.assertEqual(json.loads(preview_response.content)['encontrados'], 4)
            copy.assert_not_called()

            unconfirmed = views.copy_period_records_view(self._request('execute'), 'Generic')
            self.assertEqual(unconfirmed.status_code, 400)
            copy.assert_not_called()

            confirmed = views.copy_period_records_view(self._request('execute', 'true'), 'Generic')
            self.assertEqual(json.loads(confirmed.content)['copied'], 3)
            copy.assert_called_once()

    def test_invalid_table_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_reference_model({'tabela': 'Cadastro;DROP', 'campo_chave': 'CpfCnpj'})

    def test_duplicate_insert_returns_controlled_error(self):
        from .views import handle_form_action

        class EmptyStructureQuery:
            def exclude(self, **kwargs):
                return self

            def exists(self):
                return False

            def __iter__(self):
                return iter(())

        class MainModel:
            class Meta:
                db_table = 'Main'
                fields = [type('Field', (), {'name': 'Nome'})()]
                pk = type('PrimaryKey', (), {'name': 'id'})()

            _meta = Meta()
            objects = Mock()

        MainModel.objects.create.side_effect = IntegrityError('duplicate key')
        form = type('Form', (), {'cleaned_data': {'Nome': 'Registro'}})()
        request = type('Request', (), {'POST': {'acao': 'salvar'}})()
        with patch('app_rpps.views.RppsEstrutura.objects.filter', return_value=EmptyStructureQuery()):
            with self.assertRaisesRegex(ValueError, 'já existe'):
                handle_form_action(request, MainModel, form, None)


class TestNormalizeChaveTipo(TestCase):
    """Testes para o helper de normalização de tipo_chave_blur"""
    
    # ========= TESTES PRIMARY KEY =========
    
    def test_primary_key_pascalcase(self):
        """PrimaryKey em PascalCase deve normalizar para 'primary'"""
        self.assertEqual(normalize_chave_tipo('PrimaryKey'), 'primary')
    
    def test_primary_key_lowercase(self):
        """primary em lowercase deve permanecer 'primary'"""
        self.assertEqual(normalize_chave_tipo('primary'), 'primary')
    
    def test_primary_key_uppercase(self):
        """PRIMARY em uppercase deve normalizar para 'primary'"""
        self.assertEqual(normalize_chave_tipo('PRIMARY'), 'primary')
    
    def test_primary_key_lowercase_pascalcase(self):
        """primarykey em lowercase deve normalizar para 'primary'"""
        self.assertEqual(normalize_chave_tipo('primarykey'), 'primary')
    
    def test_primary_key_with_spaces(self):
        """Espaços em branco devem ser removidos"""
        self.assertEqual(normalize_chave_tipo('  PrimaryKey  '), 'primary')
        self.assertEqual(normalize_chave_tipo('  primary  '), 'primary')
    
    def test_primary_key_abbreviation(self):
        """pk deve normalizar para 'primary'"""
        self.assertEqual(normalize_chave_tipo('pk'), 'primary')
    
    # ========= TESTES FOREIGN KEY =========
    
    def test_foreign_key_pascalcase(self):
        """ForeignKey em PascalCase deve normalizar para 'foreign'"""
        self.assertEqual(normalize_chave_tipo('ForeignKey'), 'foreign')
    
    def test_foreign_key_lowercase(self):
        """foreign em lowercase deve permanecer 'foreign'"""
        self.assertEqual(normalize_chave_tipo('foreign'), 'foreign')
    
    def test_foreign_key_uppercase(self):
        """FOREIGN em uppercase deve normalizar para 'foreign'"""
        self.assertEqual(normalize_chave_tipo('FOREIGN'), 'foreign')
    
    def test_foreign_key_lowercase_pascalcase(self):
        """foreignkey em lowercase deve normalizar para 'foreign'"""
        self.assertEqual(normalize_chave_tipo('foreignkey'), 'foreign')
    
    def test_foreign_key_with_spaces(self):
        """Espaços em branco devem ser removidos"""
        self.assertEqual(normalize_chave_tipo('  ForeignKey  '), 'foreign')
        self.assertEqual(normalize_chave_tipo('  foreign  '), 'foreign')
    
    def test_foreign_key_abbreviation(self):
        """fk deve normalizar para 'foreign'"""
        self.assertEqual(normalize_chave_tipo('fk'), 'foreign')
    
    # ========= TESTES FOREIGN KEY COMPOSITE =========
    
    def test_foreign_key_composite_pascalcase(self):
        """ForeignKeyComposite deve normalizar para 'foreign_composite'"""
        self.assertEqual(normalize_chave_tipo('ForeignKeyComposite'), 'foreign_composite')
    
    def test_foreign_key_composite_lowercase(self):
        """foreign_composite deve permanecer 'foreign_composite'"""
        self.assertEqual(normalize_chave_tipo('foreign_composite'), 'foreign_composite')
    
    def test_foreign_key_composite_with_spaces(self):
        """Espaços em branco devem ser removidos"""
        self.assertEqual(normalize_chave_tipo('  ForeignKeyComposite  '), 'foreign_composite')
    
    # ========= TESTES OUTROS TIPOS =========
    
    def test_unique_type(self):
        """Tipo 'unique' deve permanecer 'unique'"""
        self.assertEqual(normalize_chave_tipo('unique'), 'unique')
        self.assertEqual(normalize_chave_tipo('UNIQUE'), 'unique')
    
    def test_index_type(self):
        """Tipo 'index' deve permanecer 'index'"""
        self.assertEqual(normalize_chave_tipo('index'), 'index')
        self.assertEqual(normalize_chave_tipo('INDEX'), 'index')
    
    # ========= TESTES EDGE CASES =========
    
    def test_none_value(self):
        """None deve retornar None"""
        self.assertIsNone(normalize_chave_tipo(None))
    
    def test_empty_string(self):
        """String vazia deve retornar None"""
        self.assertIsNone(normalize_chave_tipo(''))
    
    def test_whitespace_only(self):
        """Apenas espaços em branco deve retornar None"""
        self.assertIsNone(normalize_chave_tipo('   '))
    
    def test_unknown_value(self):
        """Valor desconhecido deve retornar normalizado (lowercase + trim)"""
        # Valor desconhecido não deve lançar exceção
        result = normalize_chave_tipo('unknown_type')
        self.assertEqual(result, 'unknown_type')
    
    def test_unknown_value_with_spaces(self):
        """Valor desconhecido com espaços deve ser normalizado"""
        result = normalize_chave_tipo('  UnknownType  ')
        self.assertEqual(result, 'unknowntype')


class TestIsPrimaryKeyField(TestCase):
    """Testes para is_primary_key_field"""
    
    def test_primary_key_returns_true(self):
        """PrimaryKey deve retornar True"""
        self.assertTrue(is_primary_key_field('PrimaryKey'))
    
    def test_primary_lowercase_returns_true(self):
        """primary deve retornar True"""
        self.assertTrue(is_primary_key_field('primary'))
    
    def test_foreign_key_returns_false(self):
        """ForeignKey deve retornar False"""
        self.assertFalse(is_primary_key_field('ForeignKey'))
    
    def test_none_returns_false(self):
        """None deve retornar False"""
        self.assertFalse(is_primary_key_field(None))
    
    def test_empty_string_returns_false(self):
        """String vazia deve retornar False"""
        self.assertFalse(is_primary_key_field(''))


class TestIsForeignKeyField(TestCase):
    """Testes para is_foreign_key_field"""
    
    def test_foreign_key_returns_true(self):
        """ForeignKey deve retornar True"""
        self.assertTrue(is_foreign_key_field('ForeignKey'))
    
    def test_foreign_lowercase_returns_true(self):
        """foreign deve retornar True"""
        self.assertTrue(is_foreign_key_field('foreign'))
    
    def test_foreign_key_composite_returns_true(self):
        """ForeignKeyComposite deve retornar True"""
        self.assertTrue(is_foreign_key_field('ForeignKeyComposite'))
    
    def test_primary_key_returns_false(self):
        """PrimaryKey deve retornar False"""
        self.assertFalse(is_foreign_key_field('PrimaryKey'))
    
    def test_none_returns_false(self):
        """None deve retornar False"""
        self.assertFalse(is_foreign_key_field(None))
    
    def test_empty_string_returns_false(self):
        """String vazia deve retornar False"""
        self.assertFalse(is_foreign_key_field(''))


class TestIsCompositeForeignKeyField(TestCase):
    """Testes para is_composite_foreign_key_field"""
    
    def test_composite_returns_true(self):
        """ForeignKeyComposite deve retornar True"""
        self.assertTrue(is_composite_foreign_key_field('ForeignKeyComposite'))
    
    def test_composite_lowercase_returns_true(self):
        """foreign_composite deve retornar True"""
        self.assertTrue(is_composite_foreign_key_field('foreign_composite'))
    
    def test_regular_foreign_returns_false(self):
        """ForeignKey regular deve retornar False"""
        self.assertFalse(is_composite_foreign_key_field('ForeignKey'))
    
    def test_primary_returns_false(self):
        """PrimaryKey deve retornar False"""
        self.assertFalse(is_composite_foreign_key_field('PrimaryKey'))


from .metadata_helpers import (
    get_referencia_config,
    parse_referencia_config,
    parse_tabela_referencia,
    validate_table_name,
    validate_column_name,
    validate_columns,
    validate_order_by,
)
from .forms import DynamicFormGenerator
from .models import GruposColegiados, RppsEstrutura


class TestSqlIdentifierValidation(TestCase):
    """Testes para validação rígida de nomes de tabela e coluna antes do SQL dinâmico."""

    def test_valid_table_name(self):
        self.assertEqual(validate_table_name('ResultadoAtuarial'), 'ResultadoAtuarial')

    def test_invalid_table_name_payloads_are_rejected(self):
        for value in [
            'ResultadoAtuarial;DROP TABLE X',
            'ResultadoAtuarial--',
            'ResultadoAtuarial WHERE 1=1',
            'dbo.ResultadoAtuarial WHERE 1=1',
        ]:
            with self.assertRaises(ValueError):
                validate_table_name(value)

    def test_valid_column_name(self):
        self.assertEqual(validate_column_name('ResultadoAtuarial', 'ano_ref'), 'ano_ref')

    def test_invalid_column_name_payloads_are_rejected(self):
        for value in [
            'ano_ref;DROP',
            'ano_ref--',
            'ano_ref OR 1=1',
        ]:
            with self.assertRaises(ValueError):
                validate_column_name('ResultadoAtuarial', value)

    def test_validate_columns_accepts_allowed_values(self):
        self.assertEqual(validate_columns('ResultadoAtuarial', ['ano_ref', 'mes_ref']), ['ano_ref', 'mes_ref'])

    def test_validate_order_by_accepts_allowed_metadata_fields(self):
        self.assertEqual(validate_order_by('ResultadoAtuarial', 'ano_ref DESC'), '[ano_ref] DESC')
        self.assertEqual(validate_order_by('ResultadoAtuarial', '-mes_ref'), '[mes_ref] DESC')

    def test_validate_order_by_rejects_payloads_with_sql_fragments(self):
        for value in [
            'ano_ref; DROP TABLE ResultadoAtuarial',
            'ano_ref DESC, nome_tabela--',
            'ano_ref OR 1=1',
        ]:
            with self.assertRaises(ValueError):
                validate_order_by('ResultadoAtuarial', value)


class TestDynamicIdentifierSanitization(TestCase):
    """Testes de regressão para filtros ORM e lookup de metadados perigosos."""

    def test_safe_model_filter_rejects_invalid_keys(self):
        filtros = {'ano_ref': 2024, 'bad__field': 'x', 'id': 1}
        self.assertEqual(safe_model_filter(RPPS, filtros), {'ano_ref': 2024, 'id': 1})

    def test_filter_foreignkey_options_rejects_invalid_campo_display(self):
        factory = RequestFactory()
        request = factory.get('/fk/', {'search': 'teste', 'campo_display': '__evil__'})

        from .views import filter_foreignkey_options

        response = filter_foreignkey_options(request, 'RPPS')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])


class TestReferenciaConfig(TestCase):
    """Testes para a estrutura formal de referencia_config."""

    def test_parse_referencia_config_legacy_dsl(self):
        config = parse_referencia_config('Cadastro(CpfCnpj=CPF)')
        self.assertEqual(config['tabela'], 'Cadastro')
        self.assertEqual(config['campo_tabela'], 'CpfCnpj')
        self.assertEqual(config['campo_tela'], 'CPF')
        self.assertEqual(config['filtros'], {})

    def test_parse_referencia_config_composta(self):
        config = parse_referencia_config('GruposColegiados(ano_ref=ano_ref,mes_ref=mes_ref,TipoFundo=TipoFundo)')
        self.assertEqual(config['tabela'], 'GruposColegiados')
        self.assertEqual(config['campo_tabela'], 'ano_ref')
        self.assertEqual(config['filtros']['mes_ref'], 'mes_ref')
        self.assertEqual(config['filtros']['TipoFundo'], 'TipoFundo')

    def test_get_referencia_config_prefers_structured_value(self):
        estrutura = type('EstruturaFake', (), {
            'tabela_referencia': 'Cadastro(CpfCnpj=CPF)',
            'referencia_config': {'tabela': 'Cadastro', 'campo_tabela': 'CpfCnpj', 'campo_tela': 'CPF', 'filtros': {}, 'dependencias': []}
        })()

        config = get_referencia_config(estrutura)
        self.assertEqual(config['tabela'], 'Cadastro')
        self.assertEqual(config['campo_tela'], 'CPF')


class TestParseTabelaReferencia(TestCase):
    """Testes para o DSL de tabela_referencia usado pelo projeto."""

    def test_parse_tabela_referencia_simples(self):
        self.assertEqual(parse_tabela_referencia('Cadastro'), ('Cadastro', None, None))

    def test_parse_tabela_referencia_sem_mapping(self):
        self.assertEqual(parse_tabela_referencia('Cadastro(CpfCnpj)'), ('Cadastro', 'CpfCnpj', None))

    def test_parse_tabela_referencia_com_mapping(self):
        self.assertEqual(parse_tabela_referencia('Cadastro(CpfCnpj=CPF)'), ('Cadastro', 'CpfCnpj', 'CPF'))

    def test_parse_tabela_referencia_com_alias(self):
        self.assertEqual(parse_tabela_referencia('Cadastro(CpfCnpj=CNPJAtuario)'), ('Cadastro', 'CpfCnpj', 'CNPJAtuario'))

    def test_parse_tabela_referencia_composta(self):
        self.assertEqual(
            parse_tabela_referencia('GruposColegiados(ano_ref=ano_ref,mes_ref=mesref,TipoFundo=Tipo_fundo)'),
            ('GruposColegiados', 'ano_ref', 'ano_ref,mes_ref=mesref,TipoFundo=Tipo_fundo')
        )


class TestReferenciaOptions(TestCase):
    """Testes focados em _get_referencia_options para o contrato legado do projeto."""

    def test_get_referencia_options_simples(self):
        Cadastro = __import__('app_rpps.models', fromlist=['Cadastro']).Cadastro
        Cadastro.objects.create(CpfCnpj='12345678901', Nome='Empresa Teste', Cargo='Diretor')

        generator = DynamicFormGenerator('GestorFinanceiro')
        options = generator._get_referencia_options('Cadastro(CpfCnpj=CPF)')
        self.assertIsInstance(options, list)
        self.assertTrue(options)
        self.assertEqual(options[0][0], '12345678901')

    def test_get_referencia_options_simples_alias(self):
        Cadastro = __import__('app_rpps.models', fromlist=['Cadastro']).Cadastro
        Cadastro.objects.create(CpfCnpj='22345678901', Nome='Empresa Alias', Cargo='Diretor')

        generator = DynamicFormGenerator('ResultadoAtuarial')
        options = generator._get_referencia_options('Cadastro(CpfCnpj=CPFAtuario)')
        self.assertIsInstance(options, list)
        self.assertTrue(options)
        self.assertEqual(options[0][0], '22345678901')

    def test_get_referencia_options_composta(self):
        GruposColegiados.objects.filter().delete()
        GruposColegiados.objects.create(
            ano_ref=2024,
            mes_ref=1,
            TipoFundo=1,
            Codigo=17,
            AtoInstituicao='Ato 1',
            DataAto='2024-01-01',
            VeiculoPublicacao=1,
            DataInstituicao='2024-01-02',
            TipoAto=1,
            Tipo=1,
            QuantidadeMembros=5,
        )

        generator = DynamicFormGenerator('MembroColegio')
        options = generator._get_referencia_options(
            'GruposColegiados(ano_ref=ano_ref,mes_ref=mes_ref,TipoFundo=TipoFundo)',
            dependencias={'ano_ref': 2024, 'mes_ref': 1, 'TipoFundo': 1},
        )
        self.assertIsInstance(options, list)
        self.assertTrue(options)
        self.assertIn(('17', '17'), options)

    def test_get_referencia_options_invalid(self):
        generator = DynamicFormGenerator('GestorFinanceiro')
        self.assertEqual(generator._get_referencia_options(''), [])
        self.assertEqual(generator._get_referencia_options(None), [])

    def test_get_referencia_options_not_json_legacy_contract(self):
        Cadastro = __import__('app_rpps.models', fromlist=['Cadastro']).Cadastro
        Cadastro.objects.create(CpfCnpj='32345678901', Nome='Empresa Legacy', Cargo='Diretor')

        generator = DynamicFormGenerator('GestorFinanceiro')
        result = generator._get_referencia_options('Cadastro(CpfCnpj=CPF)')
        self.assertIsInstance(result, list)
        self.assertNotEqual(result, [])
        self.assertEqual(result[0][0], '32345678901')

    def test_get_referencia_options_with_generic_dependencies(self):
        GruposColegiados.objects.filter().delete()
        GruposColegiados.objects.create(
            ano_ref=2024,
            mes_ref=1,
            TipoFundo=1,
            Codigo=15,
            AtoInstituicao='Ato 1',
            DataAto='2024-01-01',
            VeiculoPublicacao=1,
            DataInstituicao='2024-01-02',
            TipoAto=1,
            Tipo=1,
            QuantidadeMembros=5,
        )

        generator = DynamicFormGenerator('MembroColegio')
        result = generator._get_referencia_options(
            'GruposColegiados(ano_ref=ano_ref,mes_ref=mes_ref,TipoFundo=TipoFundo)',
            dependencias={'ano_ref': 2024, 'mes_ref': 1, 'TipoFundo': 1},
        )

        self.assertIsInstance(result, list)
        self.assertTrue(result)
        self.assertIn(('15', '15'), result)

    def test_get_referencia_options_uses_form_initial_values(self):
        GruposColegiados.objects.filter().delete()
        GruposColegiados.objects.create(
            ano_ref=2024,
            mes_ref=1,
            TipoFundo=1,
            Codigo=21,
            AtoInstituicao='Ato 1',
            DataAto='2024-01-01',
            VeiculoPublicacao=1,
            DataInstituicao='2024-01-02',
            TipoAto=1,
            Tipo=1,
            QuantidadeMembros=5,
        )
        GruposColegiados.objects.create(
            ano_ref=2024,
            mes_ref=2,
            TipoFundo=1,
            Codigo=22,
            AtoInstituicao='Ato 2',
            DataAto='2024-02-01',
            VeiculoPublicacao=1,
            DataInstituicao='2024-02-02',
            TipoAto=1,
            Tipo=1,
            QuantidadeMembros=5,
        )

        generator = DynamicFormGenerator('MembroColegio', initial={'ano_ref': 2024, 'mes_ref': 1, 'TipoFundo': 1})
        result = generator._get_referencia_options(
            'GruposColegiados(ano_ref=ano_ref,mes_ref=mes_ref,TipoFundo=TipoFundo)',
            campo=RppsEstrutura.objects.filter(nome_tabela='MembroColegio', nome_campo='CodigoGrupoColegiado').first(),
        )

        self.assertEqual(result, [('21', '21')])

    def test_get_referencia_options_requires_all_dependencies(self):
        GruposColegiados.objects.filter().delete()
        GruposColegiados.objects.create(
            ano_ref=2024,
            mes_ref=1,
            TipoFundo=1,
            Codigo=31,
            AtoInstituicao='Ato 1',
            DataAto='2024-01-01',
            VeiculoPublicacao=1,
            DataInstituicao='2024-01-02',
            TipoAto=1,
            Tipo=1,
            QuantidadeMembros=5,
        )

        generator = DynamicFormGenerator('MembroColegio', initial={'ano_ref': 2024})
        result = generator._get_referencia_options(
            'GruposColegiados(ano_ref=ano_ref,mes_ref=mes_ref,TipoFundo=TipoFundo)',
            campo=RppsEstrutura.objects.filter(nome_tabela='MembroColegio', nome_campo='CodigoGrupoColegiado').first(),
        )

        self.assertEqual(result, [])

