from django.contrib import admin
from .models import (
    RppsEstrutura,
    RPPS,
    CertificacaoRPPS,
    CertificadoRegularidadePrevidenciaria,
    GruposColegiados,
    MembroColegio,
    PlanoCusteio,
    ResultadoAtuarial,
    PoliticaInvestimento,
    CarteiraInvestimento,
    AcompanhamentoMetaAtuarial,
    GestorFinanceiro,
    TBveipub
)

# Personalização para RppsEstrutura
@admin.register(RppsEstrutura)
class RppsEstruturaAdmin(admin.ModelAdmin):
    list_display = ('nome_tabela', 'nome_campo', 'tipo_campo', 'tamanho', 'decimais', 'obrigatorio')
    list_filter = ('nome_tabela', 'tipo_campo')
    search_fields = ('nome_tabela', 'nome_campo')

# Personalização para RPPS
@admin.register(RPPS)
class RPPSAdmin(admin.ModelAdmin):
    list_display = ('ano_ref', 'mes_ref', 'TipoFundo', 'CNPJEnteFederativo', 'NomeEnteFederativo')
    list_filter = ('ano_ref', 'mes_ref', 'TipoFundo', 'CNPJEnteFederativo', 'CNPJRPPS')
    search_fields = ('CNPJEnteFederativo', 'NomeEnteFederativo','CNPJRPPS')

# Personalização para CertificacaoRPPS
@admin.register(CertificacaoRPPS)
class CertificacaoRPPSAdmin(admin.ModelAdmin):
    list_display = ('ano_ref', 'mes_ref', 'TipoFundo', 'CNPJEnteFederativo', 'NomeEnteFederativo', 'DataCertificacao')
    list_filter = ('ano_ref', 'mes_ref', 'TipoFundo')
    search_fields = ('CNPJEnteFederativo', 'NomeEnteFederativo')

# Personalização para CertificadoRegularidadePrevidenciaria
@admin.register(CertificadoRegularidadePrevidenciaria)
class CertificadoRegularidadePrevidenciariaAdmin(admin.ModelAdmin):
    list_display = ('ano_ref', 'mes_ref', 'TipoFundo', 'CNPJEnte', 'NomeEnte', 'Situacao')
    list_filter = ('ano_ref', 'mes_ref', 'TipoFundo')
    search_fields = ('CNPJEnte', 'NomeEnte')

# Personalização para GruposColegiados
@admin.register(GruposColegiados)
class GruposColegiadosAdmin(admin.ModelAdmin):
    list_display = ('ano_ref', 'mes_ref', 'TipoFundo', 'Codigo', 'AtoInstituicao', 'DataAto')
    list_filter = ('ano_ref', 'mes_ref', 'TipoFundo')
    search_fields = ('Codigo', 'AtoInstituicao')

# Personalização para MembroColegio
@admin.register(MembroColegio)
class MembroColegioAdmin(admin.ModelAdmin):
    list_display = ('ano_ref', 'mes_ref', 'TipoFundo', 'CodigoGrupoColegiado', 'Nome', 'CPF')
    list_filter = ('ano_ref', 'mes_ref', 'TipoFundo')
    search_fields = ('Nome', 'CPF')

# Personalização para PlanoCusteio
@admin.register(PlanoCusteio)
class PlanoCusteioAdmin(admin.ModelAdmin):
    list_display = ('ano_ref', 'mes_ref', 'TipoFundo', 'TipoMassa', 'BaseCalculoAnualAtivos')
    list_filter = ('ano_ref', 'mes_ref', 'TipoFundo')
    search_fields = ('TipoMassa',)

# Personalização para ResultadoAtuarial
@admin.register(ResultadoAtuarial)
class ResultadoAtuarialAdmin(admin.ModelAdmin):
    list_display = ('ano_ref', 'mes_ref', 'TipoFundo', 'ResultadoAtuarial', 'NomeAtuario', 'CPFAtuario')
    list_filter = ('ano_ref', 'mes_ref', 'TipoFundo')
    search_fields = ('NomeAtuario', 'CPFAtuario')

# Personalização para PoliticaInvestimento
@admin.register(PoliticaInvestimento)
class PoliticaInvestimentoAdmin(admin.ModelAdmin):
    list_display = ('TipoFundo', 'Ano', 'Segmento', 'Ativos')
    list_filter = ('TipoFundo','Ano', 'Segmento')
    search_fields = ('TipoFundo','Segmento', 'Ativos')

# Personalização para CarteiraInvestimento
@admin.register(CarteiraInvestimento)
class CarteiraInvestimentoAdmin(admin.ModelAdmin):
    list_display = ('TipoFundo', 'Mes', 'Ano', 'CNPJAtivo', 'Seguimento')
    list_filter =  ('TipoFundo','Ano','Mes','Seguimento')
    search_fields = ('CNPJAtivo', 'NomeAtivo')

# Personalização para AcompanhamentoMetaAtuarial
@admin.register(AcompanhamentoMetaAtuarial)
class AcompanhamentoMetaAtuarialAdmin(admin.ModelAdmin):
    list_display = ('TipoFundo', 'Mes', 'Ano', 'PatrimonioInicial', 'PatrimonioFinal')
    list_filter = ('Ano', 'Mes', 'TipoFundo')
    search_fields = ('Mes', 'Ano')

# Personalização para GestorFinanceiro
@admin.register(GestorFinanceiro)
class GestorFinanceiroAdmin(admin.ModelAdmin):
    list_display = ('ano_ref', 'mes_ref', 'TipoFundo', 'Nome', 'CPF', 'Cargo', 'Certificacao')
    list_filter = ('ano_ref', 'mes_ref', 'TipoFundo')
    search_fields = ('Nome', 'CPF')

# Personalização para TBveipub
@admin.register(TBveipub)
class TBveipubAdmin(admin.ModelAdmin):
    list_display = ('id', 'descricao')
    search_fields = ('descricao',)