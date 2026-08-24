from django.db import models
import json
import ast


class RppsEstrutura(models.Model):
    TIPO_CAMPO_CHOICES = [
        ('varchar', 'Texto'),
        ('varchar5', 'Números'),
        ('integer', 'Inteiro'),
        ('numeric', 'Decimal'),
        ('date', 'Data'),
        ('boolean', 'Verdadeiro/Falso'),
    ]

    TIPO_CHAVE_CHOICES = [
        ('primary', 'Chave Primária'),
        ('foreign', 'Chave Estrangeira'),
        ('unique', 'Único'),
        ('index', 'Índice'),
    ]

    id = models.AutoField(primary_key=True)
    nome_tabela = models.CharField(max_length=50, verbose_name="Nome da Tabela")
    nome_campo = models.CharField(max_length=50, verbose_name="Nome do Campo")
    tipo_campo = models.CharField(max_length=20, choices=TIPO_CAMPO_CHOICES, verbose_name="Tipo de Campo")
    tamanho = models.IntegerField(verbose_name="Tamanho", default=20)
    decimais = models.IntegerField(verbose_name="Casas Decimais", null=True, blank=True, default=0)
    obrigatorio = models.BooleanField(default=False, verbose_name="Obrigatório?")
    tabela_referencia = models.TextField(blank=True, null=True, verbose_name="Configuração de Referência")
    referencia_config = models.TextField(
                            blank=True,
                            null=True,
                            verbose_name="Configuração estruturada de referência",
                            help_text="Estrutura formal para tabela, campo de referência, filtros e dependências (armazenado como JSON)"
                            )
    label_campo = models.CharField(max_length=55, verbose_name="Rótulo do Campo")
    prenc_zeros = models.BooleanField(default=False, verbose_name="Preencher com Zeros?")
    entrada_espec = models.CharField(max_length=500, null=True, blank=True, verbose_name="Opções para Select")
    funcao_tratamento = models.CharField(
        max_length=50, 
        null=True, 
        blank=True, 
        default='',
        verbose_name="Função de Tratamento",
        help_text="Nome da função JavaScript para tratamento do campo"
    )
    ordem_campo = models.IntegerField(verbose_name="Ordem de Exibição", default=1)
    campo_blur = models.BooleanField(
        default=False,
        verbose_name="Campo Blur?",
        help_text="Indica se é um campo que dispara ações ao sair (blur)"
    )
    tipo_chave_blur = models.CharField(
        max_length=50,
        choices=TIPO_CHAVE_CHOICES,
        null=True,
        blank=True,
        default='',
        verbose_name="Tipo de Chave",
        help_text="Tipo de chave (PK, FK, etc)"
    )
    campo_chave_blur = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        default='',
        verbose_name="Campos Chave",
        help_text="Lista de campos que compõem a chave (em formato JSON)"
    )
    campo_display_referencia = models.TextField(
        null=True,
        blank=True,
        verbose_name="Mapeamento de Campos de Retorno",
        help_text="Mapeamento entre campos locais e campos da tabela de referência (ex: 'a=CPF,b=endereco,c=nome')"
    )
    campo_xml = models.BooleanField(default=False, verbose_name="campo para XML")

    class Meta:
        managed = True
        db_table = 'RppsEstrutura'
        verbose_name = 'Estrutura RPPS'
        verbose_name_plural = 'Estruturas RPPS'
        ordering = ['nome_tabela', 'ordem_campo']

    def get_referencia_config(self):
        """Retorna a configuração de referência em formato estruturado.

        Prioriza o campo novo `referencia_config`, mas mantém compatibilidade com
        os valores legados armazenados em `tabela_referencia`.
        """
        from .metadata_helpers import get_referencia_config

        config = get_referencia_config(self)
        if config and (config.get('tabela') or config.get('campo_tabela') or config.get('campo_tela')):
            if not self.referencia_config:
                self.referencia_config = json.dumps(config)
        return config

    def get_campos_chave(self):
        """Retorna lista de campos chave"""
        try:
            return ast.literal_eval(self.campo_chave_blur) if self.campo_chave_blur else []
        except (ValueError, SyntaxError):
            return []

    def get_campo_display_mapping(self):
        """
        Retorna o mapeamento de campos de retorno como dicionário.
        Aceita dois formatos:
        - Texto: 'campo_local=campo_ref,outro_local=outro_ref' -> {'campo_local': 'campo_ref', 'outro_local': 'outro_ref'}
        - JSON: '{"campo_local": "campo_ref"}' -> {'campo_local': 'campo_ref'}
        """
        if not self.campo_display_referencia:
            return {}
        
        try:
            # Tenta parsear como JSON primeiro
            mapping = json.loads(self.campo_display_referencia)
            if isinstance(mapping, dict):
                return mapping
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Se não for JSON, tenta formato texto "campo=valor,campo2=valor2"
        try:
            mapping = {}
            for item in self.campo_display_referencia.split(','):
                if '=' in item:
                    local_field, ref_field = item.strip().split('=', 1)
                    mapping[local_field.strip()] = ref_field.strip()
            return mapping
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erro ao parsear campo_display_referencia: {e}")
            return {}

    def __str__(self):
        return f"{self.nome_tabela}.{self.nome_campo} ({self.tabela_referencia} - {self.campo_chave_blur } )"


def migrar_tabela_referencia_para_json():
    """Converte valores legados em tabela_referencia para a estrutura formal em referencia_config.

    Mantém compatibilidade com o DSL atual do projeto, sem exigir migrations no schema legado.
    """
    from .metadata_helpers import parse_referencia_config

    atualizados = 0
    for estrutura in RppsEstrutura.objects.all():
        if not estrutura.tabela_referencia:
            continue

        config = parse_referencia_config(estrutura.tabela_referencia)
        if not config.get('tabela') and not config.get('campo_tabela') and not config.get('campo_tela'):
            continue

        config_json = json.dumps(config)
        if estrutura.referencia_config != config_json:
            estrutura.referencia_config = config_json
            estrutura.save(update_fields=['referencia_config'])
            atualizados += 1

    return atualizados


class EstruturaMenu(models.Model):
    TIPO_ACAO_CHOICES = [
        ('CRUD', 'Formulário CRUD'),
        ('BOTAO', 'Ação com Botão'),
        ('RELATORIO', 'Relatório'),
        ('LINK', 'Link Externo'),
    ]
    
    id = models.AutoField(primary_key=True)
    sistema = models.CharField(max_length=50, verbose_name="Nome do Sistema")
    aplicativo = models.CharField(max_length=50, verbose_name="Nome do App")
    arquivo = models.CharField(max_length=50, verbose_name="Arquivo/Modelo")
    label = models.CharField(max_length=100, verbose_name="Rótulo do Menu")
    nometemplate = models.CharField(max_length=50, verbose_name="Nome do Template")
    acao = models.CharField(max_length=50, choices=TIPO_ACAO_CHOICES, default='CRUD', verbose_name="Tipo de Ação")
    requer_permissao = models.BooleanField(default=False, verbose_name="Requer Permissão?")
    ordem_menu = models.IntegerField(default=1, verbose_name="Ordem no Menu")
    icone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Ícone (Bootstrap Icons)")
    
    class Meta:
        managed = False
        db_table = 'EstruturaMenu'
        verbose_name = 'Item de Menu'
        verbose_name_plural = 'Itens de Menu'
        ordering = ['ordem_menu', 'label']
        
    def __str__(self):
        return f"{self.label} ({self.arquivo})"

class Cadastro(models.Model):
    CpfCnpj = models.CharField(max_length=14, primary_key=True)
    Nome    = models.CharField(max_length=255)
    Cargo   = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'Cadastro'
        unique_together = [('CpfCnpj')] 
        verbose_name = 'Cadastro'
        verbose_name_plural = 'Cadastros'

    def __str__(self):
        return f"Cadastro (CpfCnpj: {self.CpfCnpj}, Nome: {self.Nome}, Cargo: {self.Cargo})"
    
class RPPS(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TipoFundo = models.IntegerField()
    CNPJEnteFederativo = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJEnteFederativo',
        related_name='rpps_ente',
        null=True,
        blank=True
    )
    NomeEnteFederativo = models.CharField(max_length=255)
    CNPJRPPS = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJRPPS',
        related_name='rpps_rpps',
        null=True,
        blank=True
    )
    DataCriacao = models.CharField(max_length=255)
    TipoAto = models.IntegerField()
    AtoCriacao = models.CharField(max_length=32)
    DataAto = models.CharField(max_length=10)
    DataPublicacao = models.CharField(max_length=10)
    VeiculoPublicacao = models.IntegerField()
    Ementa = models.CharField(max_length=255)
    TipoRegime = models.IntegerField()
    TipoMassa = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'RPPS'
        unique_together = [('ano_ref', 'mes_ref', 'TipoFundo', 'CNPJEnteFederativo', 'CNPJRPPS')]
        verbose_name = 'RPPS'
        verbose_name_plural = 'RPPS'

    def __str__(self):
        cnpj_ente = self.CNPJEnteFederativo.CpfCnpj if self.CNPJEnteFederativo else 'N/A'
        cnpj_rpps = self.CNPJRPPS.CpfCnpj if self.CNPJRPPS else 'N/A'
        return f"RPPS (Ano: {self.ano_ref}, Mês: {self.mes_ref}, TipoFundo: {self.TipoFundo}, CNPJ Ente: {cnpj_ente}, CNPJ RPPS: {cnpj_rpps})"

class CertificacaoRPPS(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TipoFundo = models.IntegerField()
    CNPJEnteFederativo = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJEnteFederativo',
        related_name='certificacao_ente',
        null=True,
        blank=True
    )
    NomeEnteFederativo = models.CharField(max_length=255)
    DataTermoAdesao = models.CharField(max_length=10)
    DataCertificacao = models.CharField(max_length=10, blank=True)
    Nivel = models.IntegerField(blank=True)
    DataValidade = models.CharField(max_length=10, blank=True )
    CNPJCertificadora = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJCertificadora',
        related_name='certificadora',
        null=True,
        blank=True
    )

    class Meta:
        managed = False
        db_table = 'CertificacaoRPPS'
        unique_together = [('ano_ref', 'mes_ref', 'TipoFundo','CNPJEnteFederativo')]  
        verbose_name = 'CertificacaoRPPS'
        verbose_name_plural = 'Membro Colegio'

    def __str__(self):
        cnpj_ente = self.CNPJEnteFederativo.CpfCnpj if self.CNPJEnteFederativo else 'N/A'
        return f"CertificacaoRPPS (Ano: {self.ano_ref}, Mês: {self.mes_ref}, TipoFundo: {self.TipoFundo}, CNPJ Ente: {cnpj_ente})"
    
    
class CertificadoRegularidadePrevidenciaria(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TipoFundo = models.IntegerField()
    CNPJEnte = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJEnte',
        related_name='certificado_ente',
        null=True,
        blank=True
    )
    NomeEnte = models.CharField(max_length=255)
    NumeroEmissao = models.CharField(max_length=32, blank=True, null=True)
    Situacao = models.IntegerField()
    DataEmissao = models.CharField(max_length=10)
    DataValidade = models.CharField(max_length=10)
    Tipo = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'CertificadoRegularidadePrevidenciaria'
        unique_together = [('ano_ref', 'mes_ref', 'TipoFundo','CNPJEnte')]  
        verbose_name = 'Certificado Regularidade Previdenciaria'
        verbose_name_plural = 'Certificados Regularidades Previdenciaria'

    def __str__(self):
        cnpj = self.CNPJEnte.CpfCnpj if self.CNPJEnte else 'N/A'
        return f"CertificadoRegularidadePrevidenciaria (Ano: {self.ano_ref}, Mês: {self.mes_ref}, TipoFundo: {self.TipoFundo}, CNPJ: {cnpj})"
    

class GruposColegiados(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TipoFundo = models.IntegerField()
    Codigo = models.IntegerField()
    AtoInstituicao = models.CharField(max_length=32)
    DataAto = models.CharField(max_length=10)
    VeiculoPublicacao = models.IntegerField()
    DataInstituicao = models.CharField(max_length=10)
    TipoAto = models.IntegerField()
    Tipo = models.IntegerField()
    QuantidadeMembros = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'GruposColegiados'  # Substitua pelo nome real da tabela
        unique_together = [('ano_ref', 'mes_ref', 'TipoFundo','Codigo')]  
        verbose_name = 'Grupos Colegiados'
        verbose_name_plural = 'Grupos Colegiados'

    def __str__(self):
        return f"GruposColegiados (Ano: {self.ano_ref}, Mês: {self.mes_ref}, TipoFundo: {self.TipoFundo}, Codigo: {self.Codigo} )"

class MembroColegio(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TipoFundo = models.IntegerField()
    CodigoGrupoColegiado = models.IntegerField()
    Nome = models.CharField(max_length=255)
    CPF = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CPF',
        related_name='membro_colegio',
        null=True,
        blank=True
    )
    DataNomeacao = models.CharField(max_length=10)
    TipoMembro = models.IntegerField()
    TipoCargo = models.IntegerField()
    Certificacao = models.IntegerField(null=True)
    Certificadora = models.IntegerField(null=True)
    DataEmissaoCertificado = models.CharField(max_length=10,null=True)
    DataValidadeCertificado = models.CharField(max_length=10,null=True)

    class Meta:
        managed = False
        db_table = 'MembroColegio'
        unique_together = [('ano_ref', 'mes_ref', 'TipoFundo','CodigoGrupoColegiado','CPF')]
        verbose_name = 'MembroColegio'
        verbose_name_plural = 'Membro Colegio'

 
    def __str__(self):
        cpf = self.CPF.CpfCnpj if self.CPF else 'N/A'
        return f"Membro Colegio (Ano: {self.ano_ref}, Mês: {self.mes_ref}, TipoFundo: {self.TipoFundo}, CodigoGrupoColegiado: {self.CodigoGrupoColegiado}, CPF: {cpf})"

class PlanoCusteio(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TipoFundo = models.IntegerField()
    TipoMassa = models.IntegerField()
    BaseCalculoAnualAtivos = models.DecimalField(max_digits=18, decimal_places=2)
    BaseCalculoAnualAposentados = models.DecimalField(max_digits=18, decimal_places=2)
    BaseCalculoAnualPensionistas = models.DecimalField(max_digits=18, decimal_places=2)
    BaseCalculoAnualDespesasAdm = models.DecimalField(max_digits=18, decimal_places=2)
    PrevisaoContribuicaoAnualPatronal = models.DecimalField(max_digits=18, decimal_places=2)
    PrevisaoContribuicaoAnualSegurado = models.DecimalField(max_digits=18, decimal_places=2)
    PrevisaoContribuicaoAnualAposentado = models.DecimalField(max_digits=18, decimal_places=2)
    PrevisaoContribuicaoAnualPensionista = models.DecimalField(max_digits=18, decimal_places=2)
    PrevisaoContribuicaoInsuficienciaFinanceira = models.DecimalField(max_digits=18, decimal_places=2)
    LimiteGastosDespesasAdm = models.DecimalField(max_digits=18, decimal_places=2)
    AliquotaSegurado = models.DecimalField(max_digits=18, decimal_places=2)
    AliquotaPatronalOrdinaria = models.DecimalField(max_digits=18, decimal_places=2)
    AliquotaPatronalExtraordinária = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'PlanoCusteio'  # Substitua pelo nome real da tabela
        unique_together = [('ano_ref', 'mes_ref', 'TipoFundo','TipoMassa')]  # Substituído por unique_together0
        verbose_name = 'Plano Custeio'
        verbose_name_plural = 'Planos Custeio'

    def __str__(self):
        return f"Plano Custeio (Ano: {self.ano_ref}, Mês: {self.mes_ref}, TipoFundo: {self.TipoFundo}, TipoMassa: {self.TipoMassa})"

class ResultadoAtuarial(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TpFundo = models.IntegerField()
    TipoFundo = models.IntegerField()
    ResultadoAtuarial = models.DecimalField(max_digits=18, decimal_places=2)
    ValorAtualRemuneracoesFuturas = models.DecimalField(max_digits=18, decimal_places=2)
    NomeAtuario = models.CharField(max_length=255)
    CPFAtuario = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CPFAtuario',
        related_name='atuario',
        null=True,
        blank=True
    )
    NumeroIBA = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'ResultadoAtuarial'
        unique_together = [('ano_ref', 'mes_ref','TpFundo','TipoFundo')]
        verbose_name = 'Resultado Atuarial'
        verbose_name_plural = 'Resultado Atuarial'

    def __str__(self):
        return f"Resultado Atuarial (Ano: {self.ano_ref}, Mês: {self.mes_ref}, TpFundo: {self.TpFundo}, TipoFundo: {self.TipoFundo})"
 
class CompensacaoPrevidenciaria(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()  # Ano de referência
    mes_ref = models.IntegerField()  # Mês de referência
    TipoFundo = models.SmallIntegerField()  # Tipo do fundo
    CNPJPagador = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJPagador',
        related_name='compensacao_pagador',
        null=True,
        blank=True
    )
    NomePagador = models.CharField(max_length=255)  # Nome do pagador
    MesReferencia = models.PositiveSmallIntegerField()  # Mês da compensação
    AnoReferencia = models.PositiveIntegerField()  # Ano da compensação
    ValorReceber = models.DecimalField(max_digits=18, decimal_places=2)  # Valor a receber
    SaldoPassivo = models.DecimalField(max_digits=18, decimal_places=2)  # Saldo passivo
    SaldoFluxo = models.DecimalField(max_digits=18, decimal_places=2)  # Saldo fluxo

    class Meta:
        managed = False
        db_table = "CompensacaoPrevidenciaria"
        constraints = [
            models.UniqueConstraint(
                fields=['ano_ref', 'mes_ref', 'TipoFundo', 'CNPJPagador'],
                name="pk_CompensacaoPrevidenciaria"
            )
        ]
    
    def __str__(self):
        return f"{self.NomePagador} - {self.AnoReferencia}/{self.MesReferencia}"
    
class Parcelamento(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()  # Ano de referência
    mes_ref = models.IntegerField()  # Mês de referência
    TipoFundo = models.IntegerField()
    CNPJOrgaoParcelamento = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJOrgaoParcelamento',
        related_name='parcelamento_orgao',
        null=True,
        blank=True
    )
    NomeOrgaoParcelamento = models.CharField(max_length=255)
    NumeroLei = models.CharField(max_length=16)
    NumeroAcordo = models.CharField(max_length=16)
    CompetenciaInicial = models.CharField(max_length=10)
    CompetenciaFinal = models.CharField(max_length=10)
    ValorTotalParcelamento = models.DecimalField(max_digits=18, decimal_places=2)
    QuantidadeParcelas = models.PositiveIntegerField()
    DataVencimento = models.CharField(max_length=10)
    Reparcelamento = models.PositiveSmallIntegerField()  
    NumeroAcordoOriginal = models.CharField(max_length=16, blank=True, null=True)
    IndexadorMonetario = models.PositiveSmallIntegerField(blank=True, null=True)
     
    class Meta:
        managed = False
        db_table = 'Parcelamento'
        unique_together = [('ano_ref', 'mes_ref','TipoFundo','CNPJOrgaoParcelamento')]
        verbose_name = 'Parcelamento'
        verbose_name_plural = 'Parcelamentos'

    def __str__(self):
        return f"Parcelamento ( TipoFundo: {self.TipoFundo}, Ano: {self.ano_ref}, Mes: {self.mes_ref}, Mes: {self.CNPJOrgaoParcelamento} )"
    
class ParcelasParcelamento(models.Model):
    id = models.AutoField(primary_key=True)
    TipoFundo = models.IntegerField()
    CNPJOrgaoParcelamento = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJOrgaoParcelamento',
        related_name='parcelas_orgao',
        null=True,
        blank=True
    )
    NomeOrgaoParcelamento = models.CharField(max_length=255)
    NumeroAcordo = models.CharField(max_length=16)
    NumeroParcela = models.PositiveSmallIntegerField()
    MesReferencia = models.IntegerField()  # Ano de referência
    AnoReferencia = models.IntegerField()  # Mês de referência
    ValorParcela = models.DecimalField(max_digits=18, decimal_places=2)
    DataVencimento = models.CharField(max_length=10)
    DataPagamento  = models.CharField(max_length=10)

     
    class Meta:
        managed = False
        db_table = 'ParcelasParcelamento'
        unique_together = [('TipoFundo', 'CNPJOrgaoParcelamento')]
        verbose_name = 'Parcelamento'
        verbose_name_plural = 'PoPArcelamentos'

    def __str__(self):
        return f"Politica Investimento ( TipoFundo: {self.TipoFundo},  CNPJ: {self.CNPJOrgaoParcelamento} )"
    
    
class PoliticaInvestimento(models.Model):
    id = models.AutoField(primary_key=True)
    TipoFundo = models.IntegerField()
    Ano = models.IntegerField()
    Segmento = models.IntegerField()
    Ativos = models.IntegerField()
    LimitePermitido = models.DecimalField(max_digits=18, decimal_places=2)
    AlocacaoRPPS = models.PositiveSmallIntegerField()

    class Meta:
        managed = False
        db_table = 'PoliticaInvestimento'
        unique_together = [('TipoFundo', 'Ano', 'Segmento')]  # Substituído por unique_together
        verbose_name = 'Politica Investimento'
        verbose_name_plural = 'Politica Investimentos'

    def __str__(self):
        return f"Politica Investimento ( TipoFundo: {self.TipoFundo}, Ano: {self.Ano}, Segmento: {self.Segmento})"


class CarteiraInvestimento(models.Model):
    id = models.AutoField(primary_key=True)
    TipoFundo = models.IntegerField()
    Mes = models.IntegerField()
    Ano = models.IntegerField()
    CNPJAtivo = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CNPJAtivo',
        related_name='carteira_ativo',
        null=True,
        blank=True
    )
    NomeAtivo = models.CharField(max_length=255)
    Seguimento = models.PositiveSmallIntegerField()
    Enquadramento = models.PositiveSmallIntegerField()
    QuantidadeCotas = models.DecimalField(max_digits=28, decimal_places=8)
    ValorCota = models.DecimalField(max_digits=28, decimal_places=8)
    PatrimonioLiquidoAtivo = models.DecimalField(max_digits=28, decimal_places=8)

    class Meta:
        managed = False
        db_table = 'CarteiraInvestimento'
        unique_together = [('TipoFundo','Ano', 'Mes','CNPJAtivo','Seguimento','Enquadramento' )]  
        verbose_name = 'Carteira Investimento'
        verbose_name_plural = 'Carteiras Investimento'
        
    def __str__(self):
        return f"Carteira Investimento (TipoFundo: {self.TipoFundo},Ano: {self.Ano}, Mês: {self.Mes},Ano: {self.CNPJAtivo}, Mês: {self.Seguimento}, Enquadramento: {self.Enquadramento})"

class AcompanhamentoMetaAtuarial(models.Model):
    id = models.AutoField(primary_key=True)
    TipoFundo = models.IntegerField()
    Mes = models.IntegerField()
    Ano = models.IntegerField()
    PatrimonioInicial = models.DecimalField(max_digits=18, decimal_places=2)
    TotalAplicacoes = models.DecimalField(max_digits=18, decimal_places=2)
    TotalResgatesAmortizacoes = models.DecimalField(max_digits=18, decimal_places=2)
    RentabilidadeCarteira = models.DecimalField(max_digits=18, decimal_places=2)
    PatrimonioFinal  = models.DecimalField(max_digits=18, decimal_places=2)
    PorcetagemRentabilidadePeriodo = models.DecimalField(max_digits=18, decimal_places=2)
    MetaAtuarial = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        managed = False
        db_table = 'AcompanhamentoMetaAtuarial'
        unique_together = [('TipoFundo','Ano', 'Mes')]  # Substituído por unique_together
        verbose_name = 'Acompanhamento Meta Atuarial'
        verbose_name_plural = 'Acompanhamento Metas Atuariais'
       
    def __str__(self):
        return f"Acompanhamento Meta Atuarial (TipoFundo: {self.TipoFundo}, Ano: {self.Ano}, Mês: {self.Mes})"


class GestorFinanceiro(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TipoFundo = models.IntegerField()
    CPF = models.ForeignKey(
        'Cadastro',
        on_delete=models.PROTECT,
        to_field='CpfCnpj',
        db_column='CPF',
        related_name='gestor_financeiro',
        null=True,
        blank=True
    )
    Nome = models.CharField(max_length=255)
    Cargo = models.CharField(max_length=255)
    Certificacao = models.PositiveSmallIntegerField()
    Certificadora = models.PositiveSmallIntegerField()
    DataEmissao = models.CharField(max_length=10)
    DataValidade = models.CharField(max_length=10)

    class Meta:
        managed = False
        db_table = 'GestorFinanceiro'
        unique_together = [('ano_ref', 'mes_ref', 'TipoFundo','CPF', 'Certificacao')]
        verbose_name = 'Gestor Financeiro'
        verbose_name_plural = 'Gestores Financeiro'
     
    def __str__(self):
        cpf = self.CPF.CpfCnpj if self.CPF else 'N/A'
        return f"GestorFinanceiro (Ano: {self.ano_ref}, Mês: {self.mes_ref}, TipoFundo: {self.TipoFundo}, CPF: {cpf})"
    


class TBveipub(models.Model):
    id = models.AutoField(primary_key=True)
    descricao = models.CharField(max_length=54)

    class Meta:   
        managed = False
        db_table = 'TBveipub'
        verbose_name = 'Veiculo Publico'
        verbose_name_plural = 'Veiculos Publico'   

    def __str__(self):
        return f"GestorFinanceiro ( TBveipub: {self.id}, Decricao: {self.descricao})"
        
class Fundo(models.Model):
    id = models.AutoField(primary_key=True)
    TipoFundo = models.IntegerField()
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()    
    Nome = models.CharField(max_length=255)
    ug = models.IntegerField()
    
    class Meta:
        managed = False
        db_table = 'Fundo'  # Substitua pelo nome real da tabela
        unique_together = [('TipoFundo','ano_ref', 'mes_ref')]
        verbose_name = 'Fundo'
        verbose_name_plural = 'Fundos'

    def __str__(self):
        return f"Fundo (Fundo:TipoFundo , Ano: {self.ano_ref}, Mês: {self.mes_ref},  nome: {self.ug})"
 
class TipoXml(models.Model):
    id = models.AutoField(primary_key=True)
    TipoXml = models.IntegerField()
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    Nomarq = models.CharField(max_length=55, blank=True, null=True)
    XmlAbertura =models.BooleanField(default=False)
    XmlEncerramento =models.BooleanField(default=False)     
    XmlMensal =models.BooleanField(default=False)
    campo_filter= models.CharField(max_length=255)
    ordem_xml = models.PositiveSmallIntegerField()
  
    class Meta:
        managed = False
        db_table = 'TipoXml'  
        unique_together = [('TipoXml','ano_ref', 'mes_ref','Nomarq')]
        verbose_name = 'Tipo do movimento para o Xml'
        verbose_name_plural = 'Tipos do movimentos para o Xml'

    def __str__(self):
        return f"Fundo (Xml: {self.TipoXml}, Ano: {self.ano_ref}, Mês: {self.mes_ref},  Tabela: {self.Nomarq})"       

class Gerxml(models.Model):
    id = models.AutoField(primary_key=True)
    ano_ref = models.IntegerField()
    mes_ref = models.IntegerField()
    TipoXml = models.IntegerField()
    TipoFundo = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'Gerxml'  # Substitua pelo nome real da tabela
        unique_together = [('ano_ref', 'mes_ref', 'TipoXml','TipoFundo')]
        verbose_name = 'Gerxml'
        verbose_name_plural = 'Gerxml'

    def __str__(self):
        return f"Gerxml (Xml:  {self.TipoXml}, Ano: {self.ano_ref}, Mês: {self.mes_ref},  Fundo: {self.TipoFundo})"
