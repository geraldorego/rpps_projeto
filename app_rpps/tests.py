from django.test import TestCase, RequestFactory
from .metadata_helpers import (
    normalize_chave_tipo,
    is_primary_key_field,
    is_foreign_key_field,
    is_composite_foreign_key_field,
    safe_model_filter,
)
from .models import RPPS


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

