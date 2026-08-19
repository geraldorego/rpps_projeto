import logging
import io
import pandas as pd
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.http import JsonResponse, HttpResponseNotFound
from django.utils.translation import gettext as _
from django.contrib import messages
from django.core.cache import cache
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from .forms import generate_dynamic_form
from .utils import get_referencia_data, format_referencia_html
from django.db import models
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone

from django.db import connection
from lxml import etree as ET # Isso permite usar pretty_print

import os
import re
from django.conf import settings
from django.apps import apps

import decimal
import datetime

from .models import (
    Cadastro, ResultadoAtuarial, RPPS, CertificadoRegularidadePrevidenciaria,
    CertificacaoRPPS, GruposColegiados, MembroColegio, PlanoCusteio,
    PoliticaInvestimento, CarteiraInvestimento, AcompanhamentoMetaAtuarial,
    CompensacaoPrevidenciaria, Parcelamento, ParcelasParcelamento,
    GestorFinanceiro, RppsEstrutura, Gerxml, EstruturaMenu
)
from .metadata_helpers import (
    is_primary_key_field,
    is_foreign_key_field,
    parse_tabela_referencia,
    validate_table_name,
    validate_column_name,
    validate_columns,
    get_allowed_columns,
)

logger = logging.getLogger(__name__)

# Mapeamento de modelos
MODEL_MAPPING = {
    'Cadastro': Cadastro,
    'RPPS': RPPS,
    'CertificacaoRPPS': CertificacaoRPPS,
    'CertificadoRegularidadePrevidenciaria': CertificadoRegularidadePrevidenciaria,
    'GruposColegiados': GruposColegiados,
    'MembroColegio': MembroColegio,
    'PlanoCusteio': PlanoCusteio,
    'ResultadoAtuarial': ResultadoAtuarial,
    'CompensacaoPrevidenciaria': CompensacaoPrevidenciaria,
    'Parcelamento': Parcelamento,
    'ParcelasParcelamento': ParcelasParcelamento,
    'PoliticaInvestimento': PoliticaInvestimento,
    'CarteiraInvestimento': CarteiraInvestimento,
    'AcompanhamentoMetaAtuarial': AcompanhamentoMetaAtuarial,
    'GestorFinanceiro': GestorFinanceiro,
    'Gerxml': Gerxml,
}

MENU_OPTIONS = list(MODEL_MAPPING.keys())

def build_model_mapping():
    model_mapping = {}
    for menu in EstruturaMenu.objects.all():
        try:
            app_label = menu.aplicativo
            model_name = menu.arquivo  
            model = apps.get_model(app_label=app_label, model_name=model_name)
            if model:
                model_mapping[menu.arquivo] = model
        except Exception as e:
            logger.error(f"Erro ao registrar modelo para {menu.arquivo}: {str(e)}")
    return model_mapping


# ======= HELPERS DE DISPLAY PARA entrada_espec =======
def _parse_select_options_espec(entrada_espec):
    """Converte entrada_espec (string) em um dict {valor: descricao}.
    Suporta:
      - JSON dict: {"1": "Fundo Previdenciário", "2": "Fundo Financeiro"}
      - Lista de tuplas literal: [(1, "Fundo Previdenciário"), (2, "Fundo Financeiro")]
      - Formato simples: "1:Fundo Previdenciário,2:Fundo Financeiro"
    """
    if not entrada_espec:
        return {}
    # Tenta JSON
    try:
        import json as _json
        data = _json.loads(entrada_espec)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    # Tenta lista de tuplas
    try:
        import ast as _ast
        lst = _ast.literal_eval(entrada_espec)
        if isinstance(lst, (list, tuple)):
            mapping = {}
            for item in lst:
                try:
                    k, v = item
                    mapping[str(k)] = str(v)
                except Exception:
                    continue
            if mapping:
                return mapping
    except Exception:
        pass
    # Tenta formato "k:v,k:v"
    mapping = {}
    try:
        for part in str(entrada_espec).split(','):
            if ':' in part:
                k, v = part.split(':', 1)
                mapping[str(k).strip()] = str(v).strip()
        return mapping
    except Exception:
        return {}


# ======= HELPERS PARA VALIDAÇÃO E EXTRAÇÃO =======
def _is_valid_table_name(nome_tabela):
    """Valida se nome_tabela é seguro (apenas letras, números e underscore)
    e se existe pelo menos uma definição na estrutura do sistema.
    """
    if not nome_tabela or not re.match(r'^[A-Za-z0-9_]+$', nome_tabela):
        return False
    return RppsEstrutura.objects.filter(nome_tabela=nome_tabela).exists()


# ========== FUNÇÕES AUXILIARES ========== 
def load_estrutura_campos(tabela):
    return {
        campo.nome_campo: campo 
        for campo in RppsEstrutura.objects.filter(nome_tabela=tabela).order_by('ordem_campo')
    }

# ========== VIEWS PRINCIPAIS ========== 
@login_required
def menu_view(request):
    all_menu_items = EstruturaMenu.objects.order_by('ordem_menu')
    
    allowed_menu_items = []
    for item in all_menu_items:
        if not item.requer_permissao:
            allowed_menu_items.append(item)
        else:
            # Construct the permission string, e.g., 'app_rpps.view_rpps'
            permission_string = f"{item.aplicativo}.view_{item.arquivo.lower()}"
            if request.user.has_perm(permission_string):
                allowed_menu_items.append(item)

    # Pass the system name from the first menu item if available
    sistema = all_menu_items.first().sistema if all_menu_items.exists() else "RPPS"

    return render(request, 'app_rpps/menu.html', {
        'menu_items': allowed_menu_items,
        'sistema': sistema
    })

def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def report_view(request, tabela):
    model = MODEL_MAPPING.get(tabela)
    if not model:
        return HttpResponseNotFound("Tabela não encontrada")

    # Get field headers from RppsEstrutura
    campos_estrutura = RppsEstrutura.objects.filter(nome_tabela=tabela).order_by('ordem_campo')
    headers = [campo.label_campo for campo in campos_estrutura]
    field_names = [campo.nome_campo for campo in campos_estrutura]

    # Filter data based on form values (using the same logic as check_record)
    campos_chave = get_campos_chave(tabela)
    filter_kwargs = build_filter_kwargs(request, tabela, campos_chave)
    
    # Remove empty filters to get all records if no filter is provided
    filter_kwargs = {k: v for k, v in filter_kwargs.items() if v is not None and v != ''}

    queryset = model.objects.filter(**filter_kwargs)

    # Get records as a list of lists
    records = list(queryset.values_list(*field_names))

    return render(request, 'app_rpps/parciais/_report_grid.html', {
        'headers': headers,
        'records': records,
    })

@login_required
def export_excel_view(request, tabela):
    """Gera Excel com as MESMAS colunas, filtros e ordem da grid do modal."""
    try:
        model = MODEL_MAPPING.get(tabela)
        if not model:
            return HttpResponseNotFound("Tabela não encontrada")

        # 1) Determina colunas visíveis e labels exatamente como a grid
        display_fields = _get_display_fields(tabela, model)
        campos_estrutura, estruturas = _get_field_labels(tabela, display_fields)

        # 2) Reaplica os mesmos filtros e ordenação da grid
        queryset = model.objects.all()
        queryset = _apply_filters(request, queryset, model, tabela, display_fields, estruturas, campos_estrutura)
        queryset = queryset.order_by('-id')

        # Apenas as colunas visíveis (sem 'id', conforme grid)
        field_names = list(display_fields)
        headers = [campos_estrutura.get(f, f.replace('_', ' ').title()) for f in field_names]

        # 3) Coleta dados e aplica descrições para campos com entrada_espec
        registros = list(queryset.values(*field_names))
        total = len(registros)
        estruturas_by_field = {e.nome_campo: e for e in estruturas}
        entrada_maps = {}
        for fname, estr in estruturas_by_field.items():
            if getattr(estr, 'entrada_espec', None):
                mapping = _parse_select_options_espec(estr.entrada_espec)
                if mapping:
                    entrada_maps[fname] = mapping
        valores = []
        for row in registros:
            linha = []
            for fname in field_names:
                val = row.get(fname)
                if fname in entrada_maps and val is not None:
                    val = entrada_maps[fname].get(str(val), val)
                linha.append(val)
            valores.append(linha)

        # 4) Monta Excel com openpyxl e aplica estilo corporativo
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Border, Side, Alignment

        wb = Workbook()
        ws = wb.active
        ws.title = 'Relatório'

        # Estilos
        azul = PatternFill(start_color='004A91', end_color='004A91', fill_type='solid')
        branco = Font(color='FFFFFF', bold=True)
        borda_fina = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        alinhamento_centro = Alignment(vertical='center')

        # Cabeçalho
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = azul
            cell.font = branco
            cell.border = borda_fina
            cell.alignment = alinhamento_centro

        # Dados
        for row_idx, row in enumerate(valores, start=2):
            for col_idx, value in enumerate(row, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = borda_fina

        # Autoajuste de colunas
        for col_idx in range(1, len(headers) + 1):
            max_length = 0
            for row_idx in range(1, total + 2):
                value = ws.cell(row=row_idx, column=col_idx).value
                length = len(str(value)) if value is not None else 0
                if length > max_length:
                    max_length = length
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max(10, min(60, max_length + 2))

        # Saída
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        timestamp = timezone.localtime().strftime('%Y%m%d_%H%M')
        filename = f'Relatorio_{tabela}_{timestamp}.xlsx'

        # Log corporativo
        logger.info(f"[RELATÓRIO] {request.user.username} exportou '{tabela}' com {total} registros em {timezone.localtime()}")

        response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.error(f"Erro ao exportar Excel de '{tabela}': {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def export_pdf_view(request, tabela):
    """Gera PDF com as MESMAS colunas, filtros e ordem da grid do modal."""
    try:
        model = MODEL_MAPPING.get(tabela)
        if not model:
            return HttpResponseNotFound("Tabela não encontrada")

        # 1) Determina colunas visíveis e labels exatamente como a grid
        display_fields = _get_display_fields(tabela, model)
        campos_estrutura, estruturas = _get_field_labels(tabela, display_fields)

        # 2) Reaplica os mesmos filtros e ordenação da grid
        queryset = model.objects.all()
        queryset = _apply_filters(request, queryset, model, tabela, display_fields, estruturas, campos_estrutura)
        queryset = queryset.order_by('-id')

        # Apenas as colunas visíveis (sem 'id')
        field_names = list(display_fields)
        headers = [campos_estrutura.get(f, f.replace('_', ' ').title()) for f in field_names]

        registros = list(queryset.values(*field_names))
        total = len(registros)
        estruturas_by_field = {e.nome_campo: e for e in estruturas}
        entrada_maps = {}
        for fname, estr in estruturas_by_field.items():
            if getattr(estr, 'entrada_espec', None):
                mapping = _parse_select_options_espec(estr.entrada_espec)
                if mapping:
                    entrada_maps[fname] = mapping
        valores = []
        for row in registros:
            linha = []
            for fname in field_names:
                val = row.get(fname)
                if fname in entrada_maps and val is not None:
                    val = entrada_maps[fname].get(str(val), val)
                linha.append(val)
            valores.append(linha)

        # 3) Monta PDF com reportlab.platypus
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import cm

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)

        story = []
        styles = getSampleStyleSheet()

        estrutura_menu = EstruturaMenu.objects.filter(arquivo=tabela).first()
        nome_tela = estrutura_menu.label if estrutura_menu else tabela
        usuario = request.user.username if request.user and request.user.is_authenticated else '-'
        gerado_em = timezone.localtime().strftime('%d/%m/%Y %H:%M')

        titulo = Paragraph(f"<b>{nome_tela}</b>", styles['Title'])
        meta = Paragraph(f"Usuário: {usuario} | Gerado em: {gerado_em}", styles['Normal'])
        story.extend([titulo, Spacer(1, 0.2*cm), meta, Spacer(1, 0.5*cm)])

        # Dados da tabela (primeira linha = cabeçalho)
        data = [headers]
        data.extend([list(map(lambda v: '' if v is None else v, row)) for row in valores])

        table = Table(data, repeatRows=1)
        # Estilos
        azul = colors.HexColor('#004a91')
        cinza = colors.HexColor('#f5f5f5')
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), azul),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
        ]

        # Linhas alternadas em cinza claro (começa em 1 pois 0 é o cabeçalho)
        for i in range(1, len(data)):
            if i % 2 == 1:
                table_style.append(('BACKGROUND', (0, i), (-1, i), cinza))

        table.setStyle(TableStyle(table_style))
        story.append(table)

        doc.build(story)
        buffer.seek(0)

        timestamp = timezone.localtime().strftime('%Y%m%d_%H%M')
        filename = f'Relatorio_{tabela}_{timestamp}.pdf'

        # Log corporativo
        logger.info(f"[RELATÓRIO] {request.user.username} exportou '{tabela}' com {total} registros em {timezone.localtime()}")

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        logger.error(f"Erro ao exportar PDF de '{tabela}': {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def dynamic_form_view(request, tabela, extra_context=None):
    """View principal para exibição do formulário dinâmico"""
    if tabela.lower() in ['favicon.ico', 'robots.txt', 'static']:
        return HttpResponseNotFound()
    
    logger.info(f"Acessando formulário para tabela: {tabela}")

    MODEL_MAPPING = build_model_mapping()
    model = MODEL_MAPPING.get(tabela)

    if not model:
        messages.error(request, f'Tabela {tabela} não encontrada no sistema')
        return redirect('menu')

    # Verifica se é modal simples (apenas formulário)
    is_simple_modal = request.GET.get('modal') == 'simple'

    # Verifica se há ID ou campos chave na URL para carregar registro existente
    record_id = request.GET.get('id')
    if record_id:
        try:
            # Usa a PK dinâmica do modelo (pode ser 'id', 'CpfCnpj', etc)
            pk_field = model._meta.pk.name
            record = model.objects.get(**{pk_field: record_id})
            
            # Se for modal simples, retorna apenas o formulário
            if is_simple_modal:
                form_class = generate_dynamic_form(tabela)
                initial_data = {field.name: getattr(record, field.name) for field in record._meta.fields}
                
                # Aplica máscaras em campos documento
                initial_data = aplicar_mascaras_initial_data(tabela, initial_data, model)
                
                form = form_class(initial=initial_data)
                
                return render(request, 'app_rpps/partials/simple_form_modal.html', {
                    'form': form,
                    'tabela': tabela,
                    'record_id': getattr(record, pk_field),
                    'pk_field': pk_field,
                })
            
            return render_form_with_record(request, tabela, record)
        except model.DoesNotExist:
            messages.warning(request, 'Registro não encontrado.')
    else:
        # Verifica campos chave
        campos_chave = get_campos_chave(tabela)
        if campos_chave:
            filter_kwargs = {}
            has_all_keys = True
            for field in campos_chave:
                value = request.GET.get(field)
                if value:
                    filter_kwargs[field] = value
                else:
                    has_all_keys = False
                    break
            
            if has_all_keys and filter_kwargs:
                try:
                    record = model.objects.filter(**filter_kwargs).first()
                    if record:
                        if is_simple_modal:
                            form_class = generate_dynamic_form(tabela)
                            initial_data = {field.name: getattr(record, field.name) for field in record._meta.fields}
                            
                            # Aplica máscaras em campos documento
                            initial_data = aplicar_mascaras_initial_data(tabela, initial_data, model)
                            
                            form = form_class(initial=initial_data)
                            
                            pk_field = model._meta.pk.name
                            return render(request, 'app_rpps/partials/simple_form_modal.html', {
                                'form': form,
                                'tabela': tabela,
                                'record_id': getattr(record, pk_field),
                                'pk_field': pk_field,
                            })
                        
                        return render_form_with_record(request, tabela, record)
                except Exception as e:
                    logger.error(f"Erro ao buscar registro: {e}")

    # Se não encontrou registro, exibe formulário vazio
    form = generate_dynamic_form(tabela)()
    
    # Se for modal simples, retorna apenas o formulário
    if is_simple_modal:
        pk_field = model._meta.pk.name
        return render(request, 'app_rpps/partials/simple_form_modal.html', {
            'form': form,
            'tabela': tabela,
            'record_id': None,
            'pk_field': pk_field,
        })
    
    return render(request, 'app_rpps/form_template.html', 
                 build_form_context(tabela, form, exists=False, 
                                  initial_context={'is_new': True}))


def filter_foreignkey_options(request, tabela_ref):
    """Endpoint para filtro AJAX das ForeignKeys"""
    search_term = request.GET.get('search', '').strip()
    campo_display = request.GET.get('campo_display', 'nome')
    
    if len(search_term) < 3:
        return JsonResponse({'results': []})
    
    model_ref = MODEL_MAPPING.get(tabela_ref)
    if not model_ref:
        return JsonResponse({'error': 'Tabela não encontrada'}, status=404)
    
    try:
        filtro = Q(**{f'{campo_display}__icontains': search_term})
        registros = model_ref.objects.filter(filtro).values('id', campo_display)[:20]
        results = [{'id': r['id'], 'text': r[campo_display]} for r in registros]
        
        return JsonResponse({'results': results})
    except Exception as e:
        logger.error(f"Erro no filtro FK {tabela_ref}: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_related_fields_data(request, tabela, campo_fk):
    """
    Endpoint AJAX para buscar dados de campos relacionados via FK.
    Retorna valores de múltiplos campos da tabela de referência conforme mapeamento.
    
    Args:
        tabela: Nome da tabela principal
        campo_fk: Nome do campo FK na tabela principal
        
    Query params:
        fk_id: ID do registro na tabela de referência
        
    Returns:
        JSON com mapeamento {campo_local: valor_da_referencia}
    """
    try:
        fk_id = request.GET.get('fk_id')
        if not fk_id:
            return JsonResponse({'error': 'ID da FK não fornecido'}, status=400)
        
        # Busca configuração do campo FK
        campo_estrutura = RppsEstrutura.objects.filter(
            nome_tabela=tabela,
            nome_campo=campo_fk
        ).first()
        
        if not campo_estrutura:
            return JsonResponse({'error': f'Campo {campo_fk} não encontrado na estrutura'}, status=404)
        
        # Obtém tabela de referência e mapeamento de campos
        tabela_referencia = campo_estrutura.tabela_referencia
        if not tabela_referencia:
            return JsonResponse({'error': 'Tabela de referência não configurada'}, status=400)
        
        # Extrai nome da tabela do formato "Tabela(CampoTabela=CampoTela)"
        nome_tabela_ref, campo_tabela, campo_tela = parse_tabela_referencia(tabela_referencia)
        
        if not nome_tabela_ref:
            return JsonResponse({'error': f'Formato inválido de tabela_referencia: {tabela_referencia}'}, status=400)
        
        model_ref = MODEL_MAPPING.get(nome_tabela_ref)
        if not model_ref:
            return JsonResponse({'error': f'Modelo {nome_tabela_ref} não encontrado'}, status=404)
        
        # Busca o registro na tabela de referência
        try:
            registro_ref = model_ref.objects.get(id=fk_id)
        except model_ref.DoesNotExist:
            return JsonResponse({'error': 'Registro não encontrado na tabela de referência'}, status=404)
        
        # Obtém mapeamento de campos (ex: {'a': 'CPF', 'b': 'endereco', 'c': 'nome'})
        mapping = campo_estrutura.get_campo_display_mapping()
        
        if not mapping:
            # Se não houver mapeamento, retorna apenas o campo padrão
            campo_display = getattr(campo_estrutura, 'campo_display_referencia', 'nome')
            return JsonResponse({
                'success': True,
                'data': {campo_fk: getattr(registro_ref, campo_display, '')}
            })
        
        # Busca valores dos campos mapeados
        data = {}
        for local_field, ref_field in mapping.items():
            try:
                valor = getattr(registro_ref, ref_field, None)
                
                # Formata valores especiais
                if valor is not None:
                    if isinstance(valor, (datetime.date, datetime.datetime)):
                        valor = valor.isoformat()
                    elif isinstance(valor, decimal.Decimal):
                        valor = float(valor)
                    
                data[local_field] = valor if valor is not None else ''
            except AttributeError:
                logger.warning(f"Campo {ref_field} não existe no modelo {tabela_referencia}")
                data[local_field] = ''
        
        logger.info(f"[FK_RELATED] Retornando dados para {campo_fk}: {data}")
        
        return JsonResponse({
            'success': True,
            'data': data,
            'tabela_referencia': tabela_referencia
        })
        
    except Exception as e:
        logger.error(f"Erro ao buscar dados relacionados: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

    
def get_filtros(request, config):
    """Extrai filtros da requisição com base na configuração do campo"""
    filtros = {}
    if config.get('campo_chave_blur'):
        try:
            conteudo = config['campo_chave_blur'].strip()
            if conteudo.startswith('(') and conteudo.endswith(')'):
                conteudo = conteudo[1:-1]
            for chave in [c.strip() for c in conteudo.split(',') if c.strip()]:
                filtros[chave] = request.GET.get(chave)
        except Exception as e:
            logger.warning(f"Erro ao processar campo_chave_blur: {str(e)}")
    return filtros

# ========== VIEWS AUXILIARES ========== 
@require_http_methods(["GET"])
def load_referencia(request, tabela, campo_ref):
    """Carrega dados de referência para campos relacionados (AJAX)"""
    try:
        cache_key = f'referencia_{tabela}_{campo_ref}_{request.GET.urlencode()}'
        if cached_data := cache.get(cache_key):
            return JsonResponse(cached_data)
        
        campo = RppsEstrutura.objects.get(nome_tabela=tabela, nome_campo=campo_ref)
        config = campo.get_referencia_config()
        
        if not config.get('tabela'):
            return JsonResponse({'error': 'Configuração de referência inválida'}, status=400)
        
        dados = get_referencia_data(config, get_filtros(request, config))
        response_data = {
            'html': format_referencia_html(dados, config),
            'config': config
        }
        
        cache.set(cache_key, response_data, timeout=300)
        return JsonResponse(response_data)
    
    except Exception as e:
        logger.error(f"Erro em load_referencia: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


logger = logging.getLogger(__name__)

@require_http_methods(["GET"])
def check_fk_field(request, tabela, campo_fk):
    """
    Busca dados na tabela de referência quando usuário sai de um campo FK.
    Retorna JSON com dados para preencher campos relacionados.
    """
    try:
        # Busca configuração do campo FK
        campo_config = RppsEstrutura.objects.filter(
            nome_tabela=tabela,
            nome_campo=campo_fk
        ).first()
        
        if not campo_config or not campo_config.tabela_referencia:
            return JsonResponse({'error': 'Campo FK não configurado'}, status=400)
        
        # Pega o valor digitado
        valor_digitado = request.GET.get(campo_fk, '').strip()
        
        if not valor_digitado:
            return JsonResponse({'error': 'Valor vazio'}, status=400)
        
        logger.info(f"[CHECK_FK] Buscando '{campo_fk}'='{valor_digitado}' em '{campo_config.tabela_referencia}'")
        
        # Parse do formato "Cadastro(CpfCnpj)"
        nome_tabela_ref, campo_pk_ref, _ = parse_tabela_referencia(campo_config.tabela_referencia)
        
        if not nome_tabela_ref or not campo_pk_ref:
            return JsonResponse({'error': 'Formato de tabela_referencia inválido'}, status=400)
        
        model_ref = MODEL_MAPPING.get(nome_tabela_ref)
        if not model_ref:
            return JsonResponse({'error': f'Modelo {nome_tabela_ref} não encontrado'}, status=400)
        
        # Remove máscara do documento antes de buscar
        valor_sem_mascara = valor_digitado.replace('.', '').replace('-', '').replace('/', '')
        
        # Busca na tabela de referência
        registro_ref = model_ref.objects.filter(**{campo_pk_ref: valor_sem_mascara}).first()
        
        if not registro_ref:
            logger.warning(f"[CHECK_FK] ❌ Registro não encontrado em '{nome_tabela_ref}' com {campo_pk_ref}={valor_sem_mascara}")
            return JsonResponse({
                'found': False,
                'message': f'Registro não encontrado em {nome_tabela_ref}'
            })
        
        logger.info(f"[CHECK_FK] ✅ Registro encontrado em '{nome_tabela_ref}': {campo_pk_ref}={valor_sem_mascara}")
        
        # Obtém mapeamento de campos
        field_mapping = campo_config.get_campo_display_mapping()
        logger.info(f"[CHECK_FK] 🗺️ Mapeamento: {field_mapping}")
        
        if not field_mapping:
            return JsonResponse({
                'found': True,
                'message': 'Registro encontrado mas sem mapeamento de campos'
            })
        
        # Preenche dados_complementares com os campos mapeados
        dados_complementares = {}
        for campo_local, campo_referencia in field_mapping.items():
            valor_ref = getattr(registro_ref, campo_referencia, None)
            if valor_ref is not None:
                dados_complementares[campo_local] = str(valor_ref)
                logger.info(f"[CHECK_FK] 📝 Mapeando: {campo_local} = {valor_ref} (de {campo_referencia})")
        
        return JsonResponse({
            'found': True,
            'data': dados_complementares,
            'message': f'Dados encontrados em {nome_tabela_ref}'
        })
        
    except Exception as e:
        logger.error(f"[CHECK_FK] Erro: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def check_record(request, tabela):
    """
    Função corporativa para checagem de registro (blur-handler).
    Compatível com HTMX (requisições assíncronas) e chamadas padrão.
    """

    model = MODEL_MAPPING.get(tabela)
    if not model:
        return JsonResponse({'error': 'Modelo não encontrado'}, status=400)
    
    estrutura_menu = get_object_or_404(EstruturaMenu, arquivo=tabela)

    try:
        # 1️⃣ Obtém campos chave (sempre necessário para renderização)
        campos_chave = get_campos_chave(tabela)
        
        # 2️⃣ Identifica filtro
        if record_id := request.GET.get('id'):
            # Usa a PK dinâmica do modelo (ex.: 'CpfCnpj' em Cadastro)
            pk_field = model._meta.pk.name
            filter_kwargs = {pk_field: record_id}
        else:
            if not campos_chave:
                return JsonResponse({'error': 'Nenhum campo chave configurado'}, status=400)
            filter_kwargs = build_filter_kwargs(request, tabela, campos_chave)

        # 3️⃣ Tratamento especial para Gerxml
        if tabela == "Gerxml":
            return gerar_xml_view(request, tabela)

        # 4️⃣ Busca de registro
        record = model.objects.filter(**filter_kwargs).first()

        # === Caso exista o registro ===
        if record:
            pk_value = getattr(record, record._meta.pk.name)
            logger.info(f"[CHECK_RECORD] Registro encontrado em '{tabela}': PK={pk_value}")
            
            # Prepara dados do registro
            record_data = {}
            campos_varchar5 = RppsEstrutura.objects.filter(nome_tabela=tabela, tipo_campo='varchar5')
            campos_documento = [
                'CPF', 'CNPJ', 'CNPJEnteFederativo', 'CNPJRPPS', 'CPFAtuario',
                'CNPJPagador', 'CNPJOrgaoParcelamento', 'CNPJAtivo', 'CpfCnpj'
            ]

            for field in record._meta.fields:
                field_name = field.name
                field_value = getattr(record, field_name)
                
                # Se o campo é uma ForeignKey para Cadastro, extrai o CpfCnpj
                if hasattr(field, 'related_model') and field.related_model and field.related_model.__name__ == 'Cadastro':
                    if field_value:
                        record_data[field_name] = aplicar_mascara_documento(field_value.CpfCnpj)
                    else:
                        record_data[field_name] = None
                elif field_name in campos_documento and field_value:
                    record_data[field_name] = aplicar_mascara_documento(field_value)
                elif isinstance(field_value, (datetime.date, datetime.datetime)):
                    record_data[field_name] = field_value.isoformat() if field_value else None
                elif isinstance(field_value, decimal.Decimal):
                    record_data[field_name] = float(field_value)
                else:
                    record_data[field_name] = field_value

            # Decisão de formato de resposta baseado nos headers
            accept_header = request.headers.get('Accept', '')
            wants_json = 'application/json' in accept_header
            is_htmx = 'Hx-Request' in request.headers
            parent_table = request.GET.get('parent_table', '')
            
            # Se requisição explicitamente pede JSON (modal FK)
            if wants_json and not is_htmx:
                logger.info(f"[CHECK_RECORD] Retornando JSON para transferência FK")
                
                # Se há parent_table, aplica mapeamento de campo_display_referencia
                mapped_data = record_data
                if parent_table:
                    logger.info(f"[CHECK_RECORD] Aplicando mapeamento para parent_table={parent_table}")
                    # Busca configuração do campo FK na tabela pai que referencia esta tabela
                    campo_fk_config = RppsEstrutura.objects.filter(
                        nome_tabela=parent_table,
                        tabela_referencia__icontains=tabela
                    ).first()
                    
                    if campo_fk_config and campo_fk_config.campo_display_referencia:
                        mapping = campo_fk_config.get_campo_display_mapping() or {}
                        try:
                            # Garante que o campo FK local receba o valor da PK da referência se não estiver no mapping
                            ref_model = MODEL_MAPPING.get(tabela)
                            ref_pk = ref_model._meta.pk.name if ref_model else 'id'
                            if campo_fk_config.nome_campo and campo_fk_config.nome_campo not in mapping:
                                mapping[campo_fk_config.nome_campo] = ref_pk
                                logger.info(f"[CHECK_RECORD] Fallback mapeado: {campo_fk_config.nome_campo} <- {ref_pk}")
                        except Exception as e:
                            logger.warning(f"[CHECK_RECORD] Falha ao aplicar fallback de PK no mapping: {e}")
                        logger.info(f"[CHECK_RECORD] Mapeamento encontrado: {mapping}")
                        
                        # Aplica mapeamento: campo_local -> valor do campo_ref
                        mapped_data = {}
                        for local_field, ref_field in mapping.items():
                            if ref_field in record_data:
                                mapped_data[local_field] = record_data[ref_field]
                                logger.info(f"[CHECK_RECORD] Mapeado: {local_field} = {record_data[ref_field]}")
                            else:
                                logger.warning(f"[CHECK_RECORD] Campo {ref_field} não encontrado em record_data")
                
                return JsonResponse({
                    'exists': True,
                    'record_id': pk_value,
                    'message': 'Registro encontrado.',
                    'acao': estrutura_menu.acao,
                    'nome_tela': estrutura_menu.label,
                    'record': mapped_data
                })
            
            # Se é HTMX (blur handler), retorna formulário completo
            elif is_htmx:
                logger.info(f"[CHECK_RECORD] Retornando formulário completo via HTMX")
                return render_form_with_record(request, tabela, record, campos_chave)
            
            # Fallback: retorna JSON
            else:
                logger.info(f"[CHECK_RECORD] Retornando JSON (fallback)")
                return JsonResponse({
                    'exists': True,
                    'record_id': pk_value,
                    'message': 'Registro encontrado. Formulário atualizado.',
                    'acao': estrutura_menu.acao,
                    'nome_tela': estrutura_menu.label,
                    'record': record_data
                })

        # === Caso NÃO exista o registro ===
        logger.info(f"[HTMX] Nenhum registro encontrado para '{tabela}' com {filter_kwargs}")

        # 🔍 SEGUNDO PASSO: Verificar tabela_referencia em CAMPOS FK (não no campo PK)
        dados_complementares = {}
        
        # Busca TODOS os campos FK que têm tabela_referencia configurado
        campos_fk = RppsEstrutura.objects.filter(
            nome_tabela=tabela,
            tabela_referencia__isnull=False
        ).exclude(tabela_referencia='')
        
        for campo_fk in campos_fk:
            # Pega o valor digitado neste campo FK específico
            valor_digitado = request.GET.get(campo_fk.nome_campo, '').strip()
            
            if valor_digitado:
                logger.info(f"[CHECK_RECORD] Buscando '{campo_fk.nome_campo}'='{valor_digitado}' em '{campo_fk.tabela_referencia}'")
                
                # Parse do formato "Cadastro(CpfCnpj)"
                nome_tabela_ref, campo_pk_ref, _ = parse_tabela_referencia(campo_fk.tabela_referencia)
                
                if nome_tabela_ref and campo_pk_ref:
                    model_ref = MODEL_MAPPING.get(nome_tabela_ref)
                    
                    if model_ref:
                        # Remove máscara do documento antes de buscar
                        valor_sem_mascara = valor_digitado.replace('.', '').replace('-', '').replace('/', '')
                        
                        # Busca na tabela de referência
                        registro_ref = model_ref.objects.filter(**{campo_pk_ref: valor_sem_mascara}).first()
                        
                        if registro_ref:
                            logger.info(f"[CHECK_RECORD] ✅ Registro encontrado em '{nome_tabela_ref}': {campo_pk_ref}={valor_sem_mascara}")
                            
                            # Obtém mapeamento de campos
                            field_mapping = campo_fk.get_campo_display_mapping()
                            logger.info(f"[CHECK_RECORD] 🗺️ Mapeamento encontrado: {field_mapping}")
                            
                            if field_mapping:
                                # Preenche dados_complementares com os campos mapeados
                                for campo_local, campo_referencia in field_mapping.items():
                                    valor_ref = getattr(registro_ref, campo_referencia, None)
                                    if valor_ref is not None:
                                        dados_complementares[campo_local] = valor_ref
                                        logger.info(f"[CHECK_RECORD] 📝 Mapeando: {campo_local} = {valor_ref} (de {campo_referencia})")
                                    else:
                                        logger.warning(f"[CHECK_RECORD] ⚠️ Campo '{campo_referencia}' não existe em {nome_tabela_ref}")
                            else:
                                logger.warning(f"[CHECK_RECORD] ⚠️ campo_display_referencia vazio ou inválido para '{campo_fk.nome_campo}'")
                        else:
                            logger.warning(f"[CHECK_RECORD] ❌ Registro não encontrado em '{nome_tabela_ref}' com {campo_pk_ref}={valor_sem_mascara}")

        if 'Hx-Request' in request.headers:
            dados = request.GET.dict()
            
            # Mescla dados digitados com dados complementares da tabela de referência
            dados_iniciais = {**dados, **dados_complementares}
            
            if dados_complementares:
                logger.info(f"[CHECK_RECORD] 📦 Dados complementares encontrados: {dados_complementares}")
                logger.info(f"[CHECK_RECORD] 📋 Dados iniciais mesclados: {dados_iniciais}")
            
            form = generate_dynamic_form(tabela)(initial=dados_iniciais)
            
            # ⚠️ IMPORTANTE: Usa build_form_context para manter botões FK e outras configs
            context = build_form_context(tabela, form, record_id=None, exists=False, initial_context={
                'form': form,
                'tabela': tabela,
                'exists': False,
                'campos_chave': campos_chave,
                'acao': estrutura_menu.acao,
                'nome_tela': estrutura_menu.label,
            })
            
            # 🔹 Retorna o template completo (com base.html) — sem quebrar HTMX
            response = render(request, 'app_rpps/form_template.html', context)
            response['HX-Trigger'] = 'formAtualizado'
            return response

        # Requisição padrão (sem HTMX)
        return JsonResponse({
            'exists': False,
            'message': 'Nenhum registro encontrado. Pode prosseguir com o cadastro.',
            'dados_referencia': dados_complementares if dados_complementares else None
        })

    except Exception as e:
        logger.error(f"Erro ao buscar registro em '{tabela}': {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

    
def read_record(request, tabela, record_id):
    """Exibe um registro existente para visualização/edição"""
    model = MODEL_MAPPING.get(tabela)
    if not model:
        messages.error(request, 'Modelo não encontrado.')
        return redirect('menu')
    
    try:
        # Usa a chave primária correta do modelo
        pk_field = model._meta.pk.name
        record = get_object_or_404(model, **{pk_field: record_id})
        return render_form_with_record(request, tabela, record)
    except Exception as e:
        logger.error(f"Erro ao ler registro: {str(e)}")
        messages.error(request, f"Erro ao carregar registro: {str(e)}")
        return redirect(reverse('dynamic_form', kwargs={'tabela': tabela}))
    

# ========== FUNÇÕES DE APOIO ========== 
def get_campos_chave(tabela):
    """
    Retorna lista de campos que fazem parte de chaves (PK ou unique_together).
    Combina campos de campo_chave_blur + unique_together do modelo.
    """
    campos_chave = []
    
    # 1. Pega campos do RppsEstrutura (campo_chave_blur)
    for campo in RppsEstrutura.objects.filter(nome_tabela=tabela, campo_chave_blur__isnull=False):
        try:
            conteudo = campo.campo_chave_blur.strip().strip('()')
            campos = [item.strip() for item in conteudo.split(',') if item.strip()]
            campos_chave.extend(campos)
        except Exception as e:
            logger.error(f"Erro ao processar campo_chave_blur: {str(e)}")
            continue
    
    # 2. Adiciona campos do unique_together do modelo Django
    model = MODEL_MAPPING.get(tabela)
    if model:
        unique_constraints = getattr(model._meta, 'unique_together', [])
        if unique_constraints:
            if isinstance(unique_constraints, (list, tuple)) and len(unique_constraints) > 0:
                unique_fields = unique_constraints[0] if isinstance(unique_constraints[0], (list, tuple)) else unique_constraints
                for field in unique_fields:
                    if field not in campos_chave:
                        campos_chave.append(field)
        
        # 3. Adiciona a chave primária se não for 'id' padrão
        pk_field = model._meta.pk.name
        if pk_field != 'id' and pk_field not in campos_chave:
            campos_chave.append(pk_field)
    
    logger.info(f'[GET_CAMPOS_CHAVE] Tabela: {tabela}, Campos chave: {campos_chave}')
    return campos_chave
    
def build_filter_kwargs(request, tabela, campos_chave):
    """Constrói os argumentos de filtro para busca com tratamento seguro"""
    filter_kwargs = {}
    data = request.POST if request.method == 'POST' else request.GET
    
    logger.info(f"[BUILD_FILTER] Tabela: {tabela}")
    logger.info(f"[BUILD_FILTER] Campos chave recebidos: {campos_chave}")
    logger.info(f"[BUILD_FILTER] Dados do request ({request.method}): {dict(data)}")
    
    for field in campos_chave:
        value = data.get(field)
        logger.info(f"[BUILD_FILTER] Processando campo '{field}': valor='{value}'")
        
        if value is None or value.strip() == '':
            logger.warning(f"Campo {field} vazio ou não fornecido - ignorando")
            continue
            
        try:
            campo_info = RppsEstrutura.objects.filter(
                nome_tabela=tabela, 
                nome_campo=field
            ).first()
            
            if not campo_info:
                logger.warning(f"Configuração do campo {field} não encontrada - tratando como string")
                filter_kwargs[field] = value
                continue
                
            if campo_info.tipo_campo.lower() in ['integer', 'int']:
                try:
                    filter_kwargs[field] = int(value)
                except (ValueError, TypeError):
                    logger.error(f"Valor inválido para campo inteiro {field}: {value}")
                    continue
                    
            elif campo_info.tipo_campo.lower() == 'boolean':
                filter_kwargs[field] = value.lower() in ['true', '1', 'yes', 'on']
            elif campo_info.tipo_campo.lower() == 'varchar5':
                filter_kwargs[field] = re.sub(r'\D', '', value)             
            else:
                filter_kwargs[field] = value
                
        except Exception as e:
            logger.error(f"Erro ao processar campo {field}: {str(e)}")
            continue
    
    logger.info(f"[BUILD_FILTER] Filtros construídos: {filter_kwargs}")
    return filter_kwargs

def render_form_with_record(request, tabela, record, campos_chave=None):
    pk_value = getattr(record, record._meta.pk.name)
    print(f"\n[RENDER_FORM] Iniciando para tabela '{tabela}' com PK={pk_value}")
    
    # Prepara os dados iniciais com formatação adequada
    initial_data = {}
    campos_varchar5 = RppsEstrutura.objects.filter(nome_tabela=tabela, tipo_campo='varchar5')
    
    # Lista de campos que devem ser formatados como CPF/CNPJ
    campos_documento = ['CPF', 'CNPJ', 'CNPJEnteFederativo', 'CNPJRPPS', 'CPFAtuario', 'CNPJPagador', 'CNPJOrgaoParcelamento', 'CNPJAtivo', 'CpfCnpj']

    # Itera sobre todos os campos do registro
    for field in record._meta.fields:
        field_name = field.name
        field_value = getattr(record, field_name)
        
        # Se o campo é uma ForeignKey para Cadastro, extrai o CpfCnpj
        if hasattr(field, 'related_model') and field.related_model and field.related_model.__name__ == 'Cadastro':
            if field_value:
                # Pega o CpfCnpj do objeto Cadastro relacionado
                initial_data[field_name] = field_value.CpfCnpj
                print(f"[RENDER_FORM] FK Campo '{field_name}': {field_value.CpfCnpj}")
            else:
                initial_data[field_name] = None
                print(f"[RENDER_FORM] FK Campo '{field_name}': NULL")
        else:
            # Para campos normais, pega o valor direto
            initial_data[field_name] = field_value
            if field_name in campos_documento:
                print(f"[RENDER_FORM] Campo normal '{field_name}': {field_value}")
    
    # Aplica formatação para campos varchar5
    for campo in campos_varchar5:
        nome_campo = campo.nome_campo
        if nome_campo in initial_data and initial_data[nome_campo]:
            # Se o campo for um dos que precisa de formatação de documento
            if nome_campo in campos_documento:
                valor_formatado = aplicar_mascara_documento(initial_data[nome_campo])
                print(f"[RENDER_FORM] Formatando '{nome_campo}': {initial_data[nome_campo]} -> {valor_formatado}")
                initial_data[nome_campo] = valor_formatado
            # Para outros campos varchar5, mantém apenas números
            else:
                initial_data[nome_campo] = re.sub(r'\D', '', str(initial_data[nome_campo]))

    print(f"[RENDER_FORM] Total de campos no initial_data: {len(initial_data)}")
    
    # Gera o form com dados iniciais formatados
    form = generate_dynamic_form(tabela)(initial=initial_data)

    # Constrói o contexto com build_form_context e sobrescreve campos_chave se fornecido
    context = build_form_context(tabela, form, pk_value, True)
    if campos_chave is not None:
        context['campos_chave'] = campos_chave
    
    print(f"[RENDER_FORM] Contexto construído com sucesso\n")
    return render(request, 'app_rpps/form_template.html', context)


def aplicar_mascara_documento(valor):
    """Aplica máscara de CPF ou CNPJ dependendo do tamanho do valor"""
    if not valor:
        return valor
    # Remove qualquer caractere não numérico
    valor_limpo = re.sub(r'\D', '', str(valor))
    if len(valor_limpo) == 11:
        return f"{valor_limpo[:3]}.{valor_limpo[3:6]}.{valor_limpo[6:9]}-{valor_limpo[9:]}"
    elif len(valor_limpo) == 14:
        return f"{valor_limpo[:2]}.{valor_limpo[2:5]}.{valor_limpo[5:8]}/{valor_limpo[8:12]}-{valor_limpo[12:]}"
    return valor

def aplicar_mascaras_initial_data(tabela, initial_data, model):
    """Aplica máscaras em campos de documento no initial_data para formulários.
    
    Args:
        tabela: Nome da tabela
        initial_data: Dict com dados iniciais do formulário
        model: Classe do modelo Django
        
    Returns:
        Dict com initial_data atualizado com máscaras aplicadas
    """
    from .models import Cadastro, RppsEstrutura
    
    # Lista de campos que são CPF/CNPJ
    campos_documento = ['CPF', 'CNPJ', 'CNPJEnteFederativo', 'CNPJRPPS', 'CPFAtuario', 
                       'CNPJPagador', 'CNPJOrgaoParcelamento', 'CNPJAtivo', 'CpfCnpj']
    
    # Busca campos varchar5 da estrutura (que são CPF/CNPJ)
    estruturas = RppsEstrutura.objects.filter(nome_tabela=tabela, tipo_campo='varchar5')
    campos_varchar5 = [e.nome_campo for e in estruturas]
    
    for field_name, value in list(initial_data.items()):
        if not value:
            continue
            
        try:
            field = model._meta.get_field(field_name)
            
            # ForeignKey para Cadastro: aplica máscara no CPF/CNPJ
            if hasattr(field, 'related_model') and field.related_model and field.related_model.__name__ == 'Cadastro':
                if isinstance(value, Cadastro):
                    initial_data[field_name] = aplicar_mascara_documento(value.CpfCnpj)
                else:
                    initial_data[field_name] = aplicar_mascara_documento(value)
            
            # Campos de documento diretos
            elif field_name in campos_documento or field_name in campos_varchar5:
                initial_data[field_name] = aplicar_mascara_documento(value)
                
        except Exception as e:
            logger.error(f"[MASCARA] Erro ao aplicar máscara em {field_name}: {e}")
            continue
    
    return initial_data

def build_form_context(tabela, form=None, record_id=None, exists=False, initial_context=None):
    """
    Constrói o contexto base para renderização de formulários. 
    
    Args:
        tabela (str): Nome da tabela/modelo
        form (Form): Instância do formulário (opcional)
        record_id (int): ID do registro se existente
        exists (bool): Flag indicando se é um registro existente
        initial_context (dict): Contexto inicial para mesclar (opcional) 
    
    Returns:
        dict: Contexto completo para o template
    """
    try:
        estrutura_menu = get_object_or_404(EstruturaMenu, arquivo=tabela)
        
        # Campos chave e ordem máxima de blur
        campos_chave = []
        max_ordem_blur = 0
        campos_foreign_keys = {}
        campos_select_config = {}
        campos_blur = []
        fk_field_mappings = {}  # Mapeamento de campos relacionados
        fk_modal_tables = {}  # Tabela de referência para abrir modal
        
        # PRIMEIRO: Processa TODOS os campos com tabela_referencia (FK)
        for campo in RppsEstrutura.objects.filter(nome_tabela=tabela).order_by('ordem_campo'):
            # Se tem tabela_referencia, adiciona ao fk_modal_tables
            if campo.tabela_referencia and campo.tabela_referencia.strip():
                # Extrai apenas o nome da tabela do formato "Tabela(CampoTabela=CampoTela)"
                nome_tabela_ref, campo_tabela, campo_tela = parse_tabela_referencia(campo.tabela_referencia)
                
                if nome_tabela_ref:
                    fk_modal_tables[campo.nome_campo] = nome_tabela_ref
                    logger.info(f"[FK_BUTTON] {campo.nome_campo} -> modal {nome_tabela_ref} (campo_tabela: {campo_tabela}, campo_tela: {campo_tela or 'todos'})")
                
                    # Obtém mapeamento de campos relacionados se existir
                    field_mapping = campo.get_campo_display_mapping()
                    if field_mapping:
                        fk_field_mappings[campo.nome_campo] = {
                            'tabela_referencia': nome_tabela_ref,
                            'tabela_referencia_dsl': campo.tabela_referencia,
                            'mapping': field_mapping
                        }
        
        # SEGUNDO: Processa campos com blur e chaves (lógica original)
        for campo in RppsEstrutura.objects.filter(nome_tabela=tabela).order_by('ordem_campo'):
            # Processa campos com blur ativado
            if campo.campo_blur:
                try:
                    campos_blur.append(campo.nome_campo)
                    max_ordem_blur = max(max_ordem_blur, campo.ordem_campo)
                    if campo.campo_chave_blur:
                        conteudo = campo.campo_chave_blur.strip()
                        
                        # Processa ForeignKeys que são chave
                        if is_foreign_key_field(campo.tipo_chave_blur) and campo.tabela_referencia:
                            # Extrai nome da tabela do formato "Tabela(CampoTabela=CampoTela)"
                            nome_tabela_ref, campo_tabela, campo_tela = parse_tabela_referencia(campo.tabela_referencia)
                            
                            if nome_tabela_ref:
                                model_ref = MODEL_MAPPING.get(nome_tabela_ref)
                            
                                if model_ref:
                                    campo_display = getattr(campo, 'campo_display_referencia', 'nome')
                                    
                                    campos_select_config[campo.nome_campo] = {
                                        'tabela_referencia': nome_tabela_ref,
                                        'campo_display': campo_display,
                                        'url_filter': f'/api/filter/{nome_tabela_ref}/',
                                        'min_length': 5,
                                        'check_url': reverse('check_record', kwargs={'tabela': tabela})
                                    }
                                    
                                    # Pre-carrega FKs apenas se não estivermos lidando com erro/HTMX
                                    if not initial_context:
                                        try:
                                            registros = model_ref.objects.all().values('id', campo_display).order_by(campo_display)
                                            campos_foreign_keys[campo.nome_campo] = list(registros)
                                        except Exception as e:
                                            logger.warning(f"Erro ao pré-carregar FK {campo.nome_campo}: {str(e)}")
                                            campos_foreign_keys[campo.nome_campo] = []
                                
                                campos_chave.append(campo.nome_campo)
                                continue
                        
                        # Processa campos PrimaryKey
                        if is_primary_key_field(campo.tipo_chave_blur):
                            if conteudo.startswith('(') and conteudo.endswith(')'):
                                conteudo = conteudo[1:-1]
                            campos_extendidos = [c.strip() for c in conteudo.split(',') if c.strip()]
                            campos_chave.extend(campos_extendidos)
                except Exception as e:
                    logger.warning(f"Erro ao processar campo: {campo.nome_campo} - {str(e)}")
                    continue

        # Constrói contexto base
        context = {
            'form': form,
            'tabela': tabela,
            'record_id': record_id,
            'exists': exists,
            'campos_chave': campos_chave,
            'max_ordem_blur': max_ordem_blur,
            'campos_foreign_keys': campos_foreign_keys,
            'campos_select_config': campos_select_config,
            'fk_field_mappings': fk_field_mappings,  # Novo campo no contexto
            'fk_modal_tables': fk_modal_tables,  # Novo: indica qual tabela abrir no modal
            'sistema': estrutura_menu.sistema,
            'aplicativo': estrutura_menu.aplicativo,
            'acao': estrutura_menu.acao,
            'nome_tela': estrutura_menu.label
        }

        # Mescla com contexto inicial se fornecido
        if initial_context:
            context.update(initial_context)

        return context

    except Exception as e:
        logger.error(f"Erro ao construir contexto do formulário: {str(e)}")
        raise

def handle_invalid_form(request, form, tabela, record_id):
    """
    Função auxiliar para lidar com formulários inválidos.
    Utiliza build_form_context para garantir consistência no contexto.
    """
    messages.warning(request, _('Por favor, corrija os erros no formulário.'))
    return render(request, 'app_rpps/form_template.html',
                 build_form_context(tabela, form, record_id, bool(record_id)))


def handle_form_action(request, model, form, record_id):
    """Processa as ações do formulário (salvar/excluir). Retorna dict com resultado."""
    from .models import Cadastro
    from django.db import IntegrityError
    import re
    
    acao = request.POST.get('acao')
    
    # Detecta a chave primária do modelo
    pk_field = model._meta.pk.name
    
    if acao == 'excluir':
        if not record_id:
            raise ValueError("ID do registro não fornecido para exclusão")
        
        try:
            # Usa a chave primária correta
            record = get_object_or_404(model, **{pk_field: record_id})
            record.delete()
            logger.info(f"Registro {record_id} excluído da tabela {model.__name__}")
            return {'success': True, 'message': 'Registro excluído com sucesso!', 'action': 'delete'}
        except IntegrityError as e:
            # Captura erro de integridade e extrai nome da tabela relacionada
            error_msg = str(e)
            logger.error(f"Erro de integridade ao excluir {model.__name__}: {error_msg}")
            
            # Tenta extrair nome da tabela do erro SQL Server
            match = re.search(r'table "dbo\.([^"]+)"', error_msg)
            if match:
                tabela_relacionada = match.group(1)
                msg = f'Não é possível excluir: existem registros relacionados na tabela "{tabela_relacionada}".'
            else:
                msg = 'Não é possível excluir: existem registros relacionados em outras tabelas.'
            
            return {'success': False, 'message': msg, 'action': 'delete'}
    
    elif acao == 'salvar':
        if not form:
            raise ValueError("Formulário não fornecido para salvamento")
            
        cleaned_data = form.cleaned_data
        print(f"\n[SAVE] Dados limpos recebidos: {cleaned_data}")
        
        # Filtra apenas campos que existem no modelo (segurança contra campos inválidos em RppsEstrutura)
        campos_validos = {f.name for f in model._meta.fields}
        cleaned_data_filtrado = {k: v for k, v in cleaned_data.items() if k in campos_validos}
        
        # Log de campos removidos (se houver)
        campos_removidos = set(cleaned_data.keys()) - set(cleaned_data_filtrado.keys())
        if campos_removidos:
            logger.warning(f"[SAVE] Campos removidos por não existirem no modelo {model.__name__}: {campos_removidos}")
            print(f"[SAVE] Campos removidos (não existem no modelo): {campos_removidos}")
        
        cleaned_data = cleaned_data_filtrado
        
        # Remove máscaras APENAS dos campos de documento (CPF/CNPJ), preservando sinais de negativo em campos numéricos
        campos_documento = ['CNPJPagador', 'CNPJEnteFederativo', 'CPF', 'CPFAtuario', 'CNPJ', 'CNPJRPPS', 
                           'CNPJOrgaoParcelamento', 'CNPJAtivo', 'CpfCnpj']
        for campo in campos_documento:
            if campo in cleaned_data and cleaned_data[campo]:
                # Remove APENAS caracteres de máscara de documento (. - /), mantendo dígitos
                cleaned_data[campo] = re.sub(r'[.\-/]', '', cleaned_data[campo])
                print(f"[SAVE] Máscara removida de '{campo}': {cleaned_data[campo]}")
        
        # Detecta a chave primária do modelo e remove máscara se for documento
        pk_field = model._meta.pk.name
        if pk_field in cleaned_data and cleaned_data[pk_field]:
            # Se a PK for um campo de documento (CPF/CNPJ), remove máscara
            pk_value_str = str(cleaned_data[pk_field])
            if re.search(r'[.\-/]', pk_value_str):  # Contém caracteres de máscara
                # Remove apenas caracteres de máscara, não todos os não-dígitos
                if pk_field in campos_documento:
                    cleaned_data[pk_field] = re.sub(r'[.\-/]', '', pk_value_str)
                    print(f"[SAVE] Máscara removida da PK '{pk_field}': {cleaned_data[pk_field]}")
        
        # Converte valores de CPF/CNPJ em instâncias de Cadastro para campos ForeignKey
        for field in model._meta.fields:
            field_name = field.name
            if field_name in cleaned_data:
                # Verifica se é uma ForeignKey para Cadastro
                if hasattr(field, 'related_model') and field.related_model and field.related_model.__name__ == 'Cadastro':
                    cpf_cnpj_valor = cleaned_data[field_name]
                    if cpf_cnpj_valor:
                        # Remove máscara se ainda houver (apenas caracteres de máscara, não dígitos)
                        cpf_cnpj_limpo = re.sub(r'[.\-/]', '', str(cpf_cnpj_valor))
                        print(f"[SAVE] FK Campo '{field_name}': buscando Cadastro com CpfCnpj={cpf_cnpj_limpo}")
                        
                        try:
                            # Busca ou cria a instância de Cadastro
                            cadastro_obj = Cadastro.objects.get(CpfCnpj=cpf_cnpj_limpo)
                            cleaned_data[field_name] = cadastro_obj
                            # Usa a chave primária correta (CpfCnpj para Cadastro, id para outros)
                            pk_value = getattr(cadastro_obj, cadastro_obj._meta.pk.name)
                            print(f"[SAVE] FK Campo '{field_name}': Cadastro encontrado (PK={pk_value})")
                        except Cadastro.DoesNotExist:
                            raise ValueError(f"CPF/CNPJ {cpf_cnpj_limpo} não encontrado na tabela Cadastro. Por favor, cadastre-o primeiro.")
                    else:
                        cleaned_data[field_name] = None

        print(f"[SAVE] Dados processados para salvar: {cleaned_data}")

        # Detecta a chave primária do modelo
        pk_field = model._meta.pk.name
        
        if record_id:
            # EDIÇÃO: Usa o record_id da URL (já sem máscara) ao invés do valor do form
            # Remove o campo PK do cleaned_data para não tentar atualizá-lo
            if pk_field in cleaned_data:
                del cleaned_data[pk_field]
                print(f"[SAVE] Campo PK '{pk_field}' removido do cleaned_data (usando record_id da URL)")
            
            # Busca o registro existente
            record = get_object_or_404(model, **{pk_field: record_id})
            
            # Atualiza apenas os outros campos
            for field, value in cleaned_data.items():
                setattr(record, field, value)
            record.save()
            print(f"[SAVE] Registro {record_id} atualizado com sucesso")
            return {'success': True, 'message': 'Registro atualizado com sucesso!', 'action': 'update', 'record_id': record_id}
        else:
            # CRIAÇÃO: Usa todos os campos do cleaned_data
            record = model.objects.create(**cleaned_data)
            # Usa a chave primária correta para exibir o ID
            pk_value = getattr(record, pk_field)
            print(f"[SAVE] Novo registro criado com {pk_field}={pk_value}")
            return {'success': True, 'message': 'Registro criado com sucesso!', 'action': 'create', 'record_id': pk_value}

def tratamento_record(request, tabela, record_id=None):
    """View unificada para tratamento de CRUD"""
    try:
        print(f'[DEBUG] tratamento_record chamado - Tabela: {tabela}, Method: {request.method}, POST data: {request.POST.dict()}')
        
        model = MODEL_MAPPING.get(tabela)
        if not model:
            messages.error(request, _('Modelo não encontrado.'))
            return redirect('menu')

        if request.method == 'POST':
            acao = request.POST.get('acao')
            print(f'[DEBUG] Ação detectada: {acao}')

            if acao == 'consultar':
                campos_chave = get_campos_chave(tabela)
                # Use request.POST instead of request.GET for build_filter_kwargs
                filter_kwargs = {}
                for field in campos_chave:
                    value = request.POST.get(field)
                    if value is not None and value.strip() != '':
                        filter_kwargs[field] = value

                record = model.objects.filter(**filter_kwargs).first()
                if record:
                    return render_form_with_record(request, tabela, record)
                else:
                    form = generate_dynamic_form(tabela)(request.POST)
                    return render(request, 'app_rpps/form_template.html', build_form_context(tabela, form, exists=False))

            if request.POST.get('acao') == 'gerar_xml':
                print('[DEBUG] Detectado acao=gerar_xml')
                return gerar_xml_view(request, tabela)                
            
            if acao == 'excluir':
                try:
                    result = handle_form_action(request, model, None, record_id)
                    # Se for AJAX, retorna JSON
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse(result)
                    messages.success(request, result.get('message', 'Registro excluído com sucesso!'))
                    return redirect(reverse('dynamic_form', kwargs={'tabela': tabela}))
                except Exception as e:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': str(e)}, status=400)
                    messages.error(request, _('Erro ao excluir registro: ') + str(e))
                    return redirect(reverse('dynamic_form', kwargs={'tabela': tabela}))
            
            form = generate_dynamic_form(tabela)(request.POST)
            if form.is_valid():
                try:
                    result = handle_form_action(request, model, form, record_id)
                    
                    # Se for AJAX, retorna JSON
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse(result)
                    
                    # Se não for AJAX, usa messages e redireciona
                    messages.success(request, result.get('message', 'Operação realizada com sucesso!'))
                    return redirect(reverse('dynamic_form', kwargs={'tabela': tabela}))
                except Exception as e:
                    # Se for AJAX, retorna JSON de erro
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': str(e)}, status=400)
                    messages.error(request, _('Erro ao processar o registro: ') + str(e))
            else:
                # Se for AJAX e form inválido, retorna o HTML do form com erros
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    # Renderiza apenas o formulário simples com erros
                    pk_field = model._meta.pk.name
                    return render(request, 'app_rpps/partials/simple_form_modal.html', {
                        'form': form,
                        'tabela': tabela,
                        'record_id': record_id,
                        'pk_field': pk_field,
                    })
                return handle_invalid_form(request, form, tabela, record_id)
        
        return redirect(reverse('dynamic_form', kwargs={'tabela': tabela}))
        
    except Exception as e:
        logger.error(f"Erro em tratamento_record: {str(e)}", exc_info=True)
        messages.error(request, _('Ocorreu um erro inesperado.'))
        return redirect('menu')


def obter_tabelas_relacionadas(tipo_xml_param):
    """
    Retorna as tabelas e filtros definidos no cadastro de TipoXml para o TipoXml informado.
    Retorna uma lista de tuplas (Nomarq, campo_filter, ordem_xml) ou uma lista vazia em caso de erro/sem dados.
    """
    try:
        if not tipo_xml_param:
            logger.warning("TipoXml não fornecido para obter_tabelas_relacionadas.")
            return []
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT Nomarq, campo_filter, ordem_xml 
                FROM [rpps].[dbo].TipoXml 
                WHERE TipoXml = %s 
                  AND campo_filter IS NOT NULL
                ORDER BY ordem_xml, mes_ref
            """, [tipo_xml_param])
            
            return cursor.fetchall()
        
    except Exception as e:
        logger.error(f"Erro ao obter tabelas relacionadas para TipoXml {tipo_xml_param}: {str(e)}", exc_info=True)
        return []
        
def buscar_registros(request, ano_ref, mes_ref, TipoFundo, nome_tabela, campo_filter, campos_xml):
    """
    Realiza a busca de registros na tabela informada,
    aplicando filtros dinâmicos definidos em campo_filter,
    incluindo a lógica especial para TipoFundo e garantindo filtros de ano e mês.
    """
    where_clauses = []
    params = []

    # Mapeamento de campos da tela para campos do SQL
    valores_tela = {
        'ano_ref': ano_ref,
        'mes_ref': mes_ref,
        'TipoFundo': TipoFundo 
    }

    tabela_validada = validate_table_name(nome_tabela)
    colunas_da_tabela = get_allowed_columns(tabela_validada)

    colunas_xml_validas = []
    for campo in campos_xml:
        try:
            colunas_xml_validas.append(validate_column_name(tabela_validada, campo))
        except ValueError as exc:
            logger.warning("Campo XML rejeitado para tabela '%s': %s", tabela_validada, campo)
            raise ValueError(f"Campo XML inválido para tabela '{tabela_validada}': {campo}") from exc

    if not colunas_xml_validas:
        raise ValueError(f"Nenhum campo XML válido encontrado para a tabela '{tabela_validada}'.")

    # Adicionar filtros obrigatórios (ano_ref, mes_ref) se existirem na tabela
    if 'ano_ref' in colunas_da_tabela:
        if valores_tela['ano_ref'] is None:
            raise ValueError(f"Filtro 'ano_ref' não informado para a tabela '{tabela_validada}'.")
        where_clauses.append(f"{connection.ops.quote_name('ano_ref')} = %s")
        params.append(valores_tela['ano_ref'])

    if 'mes_ref' in colunas_da_tabela:
        if valores_tela['mes_ref'] is None:
            raise ValueError(f"Filtro 'mes_ref' não informado para a tabela '{tabela_validada}'.")
        where_clauses.append(f"{connection.ops.quote_name('mes_ref')} = %s")
        params.append(valores_tela['mes_ref'])

    if 'TipoFundo' in colunas_da_tabela:
        if valores_tela['TipoFundo'] is None:
            raise ValueError(f"Filtro 'TipoFundo' não informado para a tabela '{tabela_validada}'.")

        if valores_tela['TipoFundo'] == '1':
            where_clauses.append(f"{connection.ops.quote_name('TipoFundo')} IN (%s, %s)")
            params.extend(['1', '5'])
        elif valores_tela['TipoFundo'] == '2':
            where_clauses.append(f"{connection.ops.quote_name('TipoFundo')} IN (%s, %s)")
            params.extend(['2', '5'])
        elif valores_tela['TipoFundo'] == '3':
            where_clauses.append(f"{connection.ops.quote_name('TipoFundo')} IN (%s)")
            params.extend(['5'])
        else:
            where_clauses.append(f"{connection.ops.quote_name('TipoFundo')} = %s")
            params.append(valores_tela['TipoFundo'])

    if campo_filter:
        try:
            if campo_filter.strip():
                filtros_adicionais_config = dict(item.strip().split('=') for item in campo_filter.split(',') if '=' in item)

                for campo_sql, campo_tela in filtros_adicionais_config.items():
                    campo_sql_validado = validate_column_name(tabela_validada, campo_sql)
                    if campo_sql_validado not in ['ano_ref', 'mes_ref', 'TipoFundo']:
                        valor = valores_tela.get(campo_tela)
                        if valor is None and request:
                            valor = request.GET.get(campo_tela)
                        if valor is None:
                            logger.warning("Filtro adicional '%s' (SQL: %s) não informado para a busca da tabela '%s'. Ignorando.", campo_tela, campo_sql_validado, tabela_validada)
                            continue

                        where_clauses.append(f"{connection.ops.quote_name(campo_sql_validado)} = %s")
                        params.append(valor)
        except ValueError as exc:
            logger.warning("campo_filter rejeitado para tabela '%s': %s", tabela_validada, campo_filter)
            raise ValueError(f"campo_filter inválido para tabela '{tabela_validada}': {campo_filter}") from exc
        except Exception as exc:
            logger.error("Erro ao parsear campo_filter '%s' para tabela '%s': %s", campo_filter, tabela_validada, exc, exc_info=True)
            raise ValueError(f"campo_filter inválido para tabela '{tabela_validada}'") from exc

    campos_str = ', '.join(connection.ops.quote_name(campo) for campo in colunas_xml_validas)
    where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'

    query = f"""
        SELECT {campos_str}
        FROM {connection.ops.quote_name(tabela_validada)}
        WHERE {where_sql}
    """

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()

def obter_dados_fundo(ano_ref, mes_ref, TipoFundo):
    """Obtém os dados básicos do fundo (Codigo, Exercicio, Mes)"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT [ano_ref] as Exercicio
                      ,[mes_ref] as Mes
                      ,[ug] as Codigo
                FROM [rpps].[dbo].[Fundo]
                WHERE ano_ref = %s
                  AND mes_ref = %s
                  AND TipoFundo = %s
            """, [ano_ref, mes_ref, TipoFundo])
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Erro ao buscar dados do fundo: {e}", exc_info=True)
        return None
    
def gerar_arquivo_xml(nome_tabela, campos_xml, registros, dados_fundo, TipoFundo=None):
    """
    Gera arquivo XML SIAP seguindo regras obrigatórias Base44:
    1. SEMPRE preenche Codigo (UG), Exercicio (ano), Mes (2 dígitos)
    2. Se houver registros: adiciona dentro de tag <nome_tabela>
    3. Se não houver: apenas Codigo, Exercicio, Mes dentro de <SIAP>
    4. Por TipoFundo:
       - 1: SÓ Previdenciario (UG=130570)
       - 2: SÓ Financeiro (UG=130571)
       - 3: SÓ Alagoas Previdencia (UG=130572)
       - 4: TODOS (3 blocos <SIAP> separados)
       - 5: Todos EXCETO 3 (2 blocos: 1+2)
    """
    try:
        print(f'[DEBUG-GERAR-XML] Tabela: {nome_tabela}, TipoFundo: {TipoFundo}')
        print(f'[DEBUG-GERAR-XML] dados_fundo: {dados_fundo}')
        print(f'[DEBUG-GERAR-XML] Qtd registros: {len(registros) if registros else 0}')
        
        # Mapeamento UG por TipoFundo
        mapa_ug = {
            1: 130570,  # Previdenciário
            2: 130571,  # Financeiro
            3: 130572,  # Alagoas Previdência
        }
        
        # Determina quais UGs precisam ser gerados
        ugs_para_gerar = []
        if TipoFundo == 1:
            ugs_para_gerar = [1]
        elif TipoFundo == 2:
            ugs_para_gerar = [2]
        elif TipoFundo == 3:
            ugs_para_gerar = [3]
        elif TipoFundo == 4:
            ugs_para_gerar = [1, 2, 3]  # TODOS
        elif TipoFundo == 5:
            ugs_para_gerar = [1, 2]  # Todos EXCETO 3
        else:
            # Fallback: usa dados_fundo se TipoFundo não for reconhecido
            if dados_fundo and len(dados_fundo) >= 3:
                ugs_para_gerar = [TipoFundo]
            else:
                print(f'[DEBUG-GERAR-XML] ⚠️ TipoFundo inválido e dados_fundo incompleto!')
                return False
        
        exercicio = str(dados_fundo[0]) if (dados_fundo and dados_fundo[0]) else None
        mes = str(dados_fundo[1]).zfill(2) if (dados_fundo and dados_fundo[1]) else None
        
        if not exercicio or not mes:
            print(f'[DEBUG-GERAR-XML] ❌ ERRO: Exercicio ou Mes faltando!')
            return False
        
        # Se TipoFundo != 4 e != 5, gera apenas um SIAP
        # Se TipoFundo == 4 ou 5, precisa gerar múltiplos XMLs (um arquivo por UG)
        if TipoFundo in [4, 5]:
            # Para TipoFundo 4 e 5, vai gerar múltiplos arquivos/XMLs
            xml_contents = []
            for tipo_ug in ugs_para_gerar:
                ug = mapa_ug[tipo_ug]
                xml_str = _gerar_siap_bloco(nome_tabela, campos_xml, registros, exercicio, mes, ug)
                xml_contents.append(xml_str)
            
            # Combina todos os blocos em um único arquivo
            xml_completo = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' + '\n'.join(xml_contents)
        else:
            # Para TipoFundo 1, 2, 3: gera um único SIAP com o UG correto
            ug = dados_fundo[2] if (dados_fundo and len(dados_fundo) >= 3) else mapa_ug.get(TipoFundo)
            xml_completo = _gerar_siap_bloco(nome_tabela, campos_xml, registros, exercicio, mes, ug)
        
        # Salva arquivo
        xml_filename = f"{nome_tabela}.xml"
        output_dir = settings.MEDIA_ROOT
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        xml_path = os.path.join(output_dir, xml_filename)
        
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(xml_completo)
        
        logger.info(f"✅ XML para '{nome_tabela}' gerado com sucesso em '{xml_path}'")
        print(f'[DEBUG-GERAR-XML] ✅ Arquivo gerado: {xml_path}')
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar XML para {nome_tabela}: {e}", exc_info=True)
        print(f'[DEBUG-GERAR-XML] ❌ ERRO: {str(e)}')
        return False


def _gerar_siap_bloco(nome_tabela, campos_xml, registros, exercicio, mes, ug):
    """
    Gera um bloco <SIAP> único com os dados especificados.
    Segue regras:
    - Se houver registros: <SIAP><Codigo>...</Codigo>...<Nome_Tabela>...</Nome_Tabela></SIAP>
    - Se não houver: <SIAP><Codigo>...</Codigo><Exercicio>...</Exercicio><Mes>...</Mes></SIAP>
    """
    root = ET.Element("SIAP")
    
    # SEMPRE adiciona cabeçalho (Codigo, Exercicio, Mes)
    ET.SubElement(root, "Codigo").text = str(ug)
    ET.SubElement(root, "Exercicio").text = str(exercicio)
    ET.SubElement(root, "Mes").text = str(mes).zfill(2)
    
    # Se houver registros, adiciona tag da tabela
    if registros:
        for reg_data in registros:
            record_element = ET.SubElement(root, nome_tabela)
            
            for i, campo_nome in enumerate(campos_xml):
                valor_campo = None
                if i < len(reg_data):
                    valor_campo = reg_data[i]
                
                campo_element = ET.SubElement(record_element, campo_nome)
                
                if valor_campo is not None:
                    if isinstance(valor_campo, (float, decimal.Decimal)):
                        campo_element.text = "{0:.2f}".format(valor_campo)
                    elif isinstance(valor_campo, datetime.date):
                        campo_element.text = valor_campo.isoformat()
                    elif isinstance(valor_campo, int):
                        campo_element.text = str(valor_campo)
                    else:
                        campo_element.text = str(valor_campo)
                else:
                    campo_element.text = ""
    
    # Converte para string formatada
    xml_str_bytes = ET.tostring(root, encoding='UTF-8', pretty_print=True)
    return xml_str_bytes.decode('utf-8')

def _handle_xml_generation_error(request, resultado, nome_tabela, dados_fundo, exception, TipoFundo=None):
    logger.error(f"Erro ao processar a tabela {nome_tabela}: {exception}", exc_info=True)
    xml_gerado = gerar_arquivo_xml(nome_tabela, [], [], dados_fundo, TipoFundo)
    resultado.append({
        'nome_tabela': nome_tabela,
        'vazia': True,
        'registros_count': 0,
        'xml_gerado': xml_gerado,
        'mensagem': f'Erro durante o processamento: {exception}. Gerado apenas cabeçalho.'
    })

def _process_xml_generation(request, nome_tabela, campo_filter, dados_fundo, ano_ref, mes_ref, TipoFundo):
    """Processes the XML generation for a single table."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT nome_campo 
            FROM [rpps].[dbo].RPPSEstrutura 
            WHERE nome_tabela = %s AND campo_xml = 1 
            ORDER BY ordem_campo
        """, [nome_tabela])
        campos_xml = [row[0] for row in cursor.fetchall()]
    logger.info(f'-----> OK: Campos XML para {nome_tabela} obtidos.')

    if not campos_xml:
        logger.warning(f"Nenhum campo XML configurado para a tabela '{nome_tabela}'. Gerando apenas o cabeçalho SIAP.")
        xml_gerado = gerar_arquivo_xml(nome_tabela, [], [], dados_fundo, TipoFundo)
        return {
            'nome_tabela': nome_tabela,
            'vazia': True,
            'registros_count': 0,
            'xml_gerado': xml_gerado,
            'mensagem': 'Nenhum campo XML configurado, gerado apenas cabeçalho.'
        }

    try:
        logger.info(f'Buscando registros para {nome_tabela} com filtros: ano={ano_ref}, mes={mes_ref}, TipoFundo={TipoFundo}, campo_filter={campo_filter}')
        registros = buscar_registros(request, ano_ref, mes_ref, TipoFundo, nome_tabela, campo_filter, campos_xml)
        logger.info(f'Registros encontrados para {nome_tabela}: {len(registros)}')
        
        xml_gerado = gerar_arquivo_xml(nome_tabela, campos_xml, registros, dados_fundo, TipoFundo)
        
        return {
            'nome_tabela': nome_tabela,
            'vazia': len(registros) == 0,
            'registros_count': len(registros),
            'xml_gerado': xml_gerado
        }
    except (ValueError, Exception) as e:
        _handle_xml_generation_error(request, [], nome_tabela, dados_fundo, e, TipoFundo)
        return {
            'nome_tabela': nome_tabela,
            'vazia': True,
            'registros_count': 0,
            'xml_gerado': False,
            'mensagem': f'Erro durante o processamento: {e}.'
        }

def gerar_xml_view(request, tabela):
    try:
        # DEBUG COMPLETO
        print(f'[DEBUG-XML] ========== INÍCIO gerar_xml_view ==========')
        print(f'[DEBUG-XML] Tabela: {tabela}')
        print(f'[DEBUG-XML] Método: {request.method}')
        print(f'[DEBUG-XML] POST completo: {dict(request.POST)}')
        print(f'[DEBUG-XML] GET completo: {dict(request.GET)}')
        print(f'[DEBUG-XML] ============================================')
        
        resultado = []
        
        # Tenta buscar dados do POST primeiro, depois do GET
        ano_ref = request.POST.get('ano_ref') or request.GET.get('ano_ref')
        mes_ref = request.POST.get('mes_ref') or request.GET.get('mes_ref')
        TipoXml = request.POST.get('TipoXml') or request.GET.get('TipoXml')
        TipoFundo = request.POST.get('TipoFundo') or request.GET.get('TipoFundo')
        
        print(f'[DEBUG] CHEGUEI 1 - Início da geração de XMLs')
        print(f'[DEBUG] Parâmetros recebidos: ano_ref={ano_ref}, mes_ref={mes_ref}, TipoXml={TipoXml}, TipoFundo={TipoFundo}')
        
        # Converte parâmetros para inteiros
        try:
            ano_ref = int(ano_ref) if ano_ref else None
            mes_ref = int(mes_ref) if mes_ref else None
            TipoXml = int(TipoXml) if TipoXml else None
            TipoFundo = int(TipoFundo) if TipoFundo else None
        except (ValueError, TypeError) as e:
            mensagem_erro = f"Erro ao converter parâmetros para inteiros: {str(e)}"
            print(f'[DEBUG] ERRO: {mensagem_erro}')
            messages.error(request, mensagem_erro)
            return redirect('menu')
        
        # Valida se todos os parâmetros foram fornecidos
        if not all([ano_ref, mes_ref, TipoXml, TipoFundo]):
            mensagem_erro = f"Parâmetros faltando - ano_ref: {ano_ref}, mes_ref: {mes_ref}, TipoXml: {TipoXml}, TipoFundo: {TipoFundo}"
            print(f'[DEBUG] ERRO: {mensagem_erro}')
            messages.error(request, mensagem_erro)
            return redirect('menu')
        
        dados_fundo = obter_dados_fundo(ano_ref, mes_ref, TipoFundo)
        print(f'[DEBUG] CHEGUEI 2 - Dados do fundo obtidos: {dados_fundo}')
        
        tabelas = obter_tabelas_relacionadas(TipoXml)
        print(f'[DEBUG] CHEGUEI 3 - Tabelas relacionadas: {tabelas}')
        
        if not tabelas:
            messages.info(request, "Nenhuma tabela configurada para este TipoXml ou TipoXml não fornecido.")
            return redirect('menu')

        for nome_tabela, campo_filter, ordem in tabelas:
            logger.info(f"Processando tabela: {nome_tabela}")
            result = _process_xml_generation(request, nome_tabela, campo_filter, dados_fundo, ano_ref, mes_ref, TipoFundo)
            resultado.append(result)

        sucesso = all(item['xml_gerado'] for item in resultado)
        erros = [item['nome_tabela'] for item in resultado if not item['xml_gerado']]
        
        if sucesso:
            messages.success(request, f"Arquivos XML gerados com sucesso para {len(resultado)} tabelas!")
        elif erros:
            messages.warning(request, f"Erro ao gerar XML para {len(erros)} tabelas: {', '.join(erros)}")
        else:
            messages.info(request, "Nenhum arquivo XML foi gerado.")

        return redirect('menu')

    except Exception as e:
        logger.error(f"Erro geral ao processar XMLs: {str(e)}", exc_info=True)
        messages.error(request, f"Erro ao processar XMLs: {str(e)}")
        return redirect('menu')


def get_str_fields(model):
    """
    Extrai os campos mencionados no método __str__ do modelo.
    Exemplo: Se __str__ retorna f"RPPS (Ano: {self.ano_ref}, Mês: {self.mes_ref})"
    Retorna ['ano_ref', 'mes_ref']
    """
    import inspect
    import re
    
    # Obtém o código fonte do método __str__
    source = inspect.getsource(model.__str__)
    
    # Procura por padrões como {self.campo} ou {self['campo']}
    pattern = r"\{self\.([A-Za-z0-9_]+)\}|\{self\[['\"]([A-Za-z0-9_]+)['\"]\]\}"
    matches = re.finditer(pattern, source)

    fields = []
    for match in matches:
        field = match.group(1) or match.group(2)
        if field:
            fields.append(field)
    
    return fields

def _get_display_fields(menu_option, model):
    try:
        estruturas = RppsEstrutura.objects.filter(nome_tabela=menu_option).order_by('ordem_campo')
        display_fields = [estrutura.nome_campo for estrutura in estruturas if estrutura.nome_campo]
        if display_fields:
            return display_fields
    except Exception as e:
        logger.error(f"--- DEBUG: Erro ao obter campos da estrutura: {e}")

    try:
        estrutura = RppsEstrutura.objects.filter(nome_tabela=menu_option).first()
        if estrutura:
            display_fields = estrutura.get_campos_chave()
            if display_fields:
                return display_fields
    except Exception as e:
        logger.error(f"--- DEBUG: Erro ao obter campos alternativos: {e}")

    return ['id']

def _get_field_labels(menu_option, display_fields):
    campos_estrutura = {}
    estruturas = RppsEstrutura.objects.filter(
        nome_tabela=menu_option,
        nome_campo__in=display_fields
    )
    for estrutura in estruturas:
        campos_estrutura[estrutura.nome_campo] = estrutura.label_campo
        
    for field in display_fields:
        if field not in campos_estrutura:
            campos_estrutura[field] = field.replace('_', ' ').title()
    return campos_estrutura, estruturas

def _apply_filters(request, queryset, model, menu_option, display_fields, estruturas, campos_estrutura):
    
    unique_together = getattr(model._meta, 'unique_together', [])
    if not unique_together and hasattr(model._meta, 'constraints'):
        for constraint in model._meta.constraints:
            if isinstance(constraint, models.UniqueConstraint):
                unique_together = [constraint.fields]
                break
    
    if not unique_together:
        campos_chave = get_campos_chave(menu_option)
        if campos_chave:
            unique_together = [campos_chave]
    
    
    filtros = {}
    if unique_together:
        campos_unique = unique_together[0]
        for field in campos_unique:
            value = request.GET.get(field)
            # Ignora valores vazios ou zero conforme solicitado
            if value is None or value == '' or value == '0':
                continue
            field_type = model._meta.get_field(field).get_internal_type()
            if field_type in ['IntegerField', 'AutoField', 'BigIntegerField']:
                try:
                    ivalue = int(value)
                    if ivalue == 0:
                        continue
                    filtros[field] = ivalue
                except ValueError:
                    continue
            else:
                filtros[field] = value
    
    for field in display_fields:
        campo_info = estruturas.filter(nome_campo=field).first()
        value = request.GET.get(field)
        if value not in [None, '', '0']:
            campo_info = estruturas.filter(nome_campo=field).first()
            if campo_info and campo_info.tipo_campo.lower() in ['integer', 'int']:
                try:
                    valor_int = int(value)
                    if valor_int != 0:
                        filtros[field] = valor_int
                except ValueError:
                    parent_value = request.GET.get(f'id_{field}')
                    if parent_value not in [None, '', '0']:
                        try:
                            ival = int(parent_value)
                            if ival != 0:
                                filtros[field] = ival
                        except ValueError:
                            pass
            else:
                parent_value = request.GET.get(f'id_{field}') or value
                if parent_value not in [None, '', '0']:
                    filtros[field] = parent_value
        else:
            parent_value = request.GET.get(f'id_{field}')
            if parent_value not in [None, '', '0']:
                if campo_info and campo_info.tipo_campo.lower() in ['integer', 'int']:
                    try:
                        ival = int(parent_value)
                        if ival != 0:
                            filtros[field] = ival
                    except ValueError:
                        pass
                else:
                    filtros[field] = parent_value

    # Log amigável dos filtros aplicados
    try:
        logger.info(f"Filtros aplicados em {menu_option}: {filtros}")
    except Exception:
        pass

    if filtros:
        queryset = queryset.filter(**filtros)
    return queryset

@login_required
def modal_grid_view(request, menu_option):
    
    try:
        model = MODEL_MAPPING.get(menu_option)
        if not model:
            logger.error("--- DEBUG: ERRO: Modelo não encontrado ---")
            return HttpResponseNotFound("Tabela não encontrada")

        display_fields = _get_display_fields(menu_option, model)
        campos_estrutura, estruturas = _get_field_labels(menu_option, display_fields)
        
        queryset = model.objects.all()
        queryset = _apply_filters(request, queryset, model, menu_option, display_fields, estruturas, campos_estrutura)

        queryset = queryset.order_by('-id').values('id', *display_fields)

        # Log do SQL gerado para depuração
        try:
            logger.info(f"SQL gerado (modal_grid {menu_option}): {str(queryset.query)}")
        except Exception:
            pass

        paginator = Paginator(queryset, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Substitui valores de campos com entrada_espec por suas descrições
        try:
            estruturas_by_field = {e.nome_campo: e for e in estruturas}
            entrada_maps = {}
            for fname, estr in estruturas_by_field.items():
                if getattr(estr, 'entrada_espec', None):
                    mapping = _parse_select_options_espec(estr.entrada_espec)
                    if mapping:
                        entrada_maps[fname] = mapping
            if entrada_maps:
                for row in page_obj.object_list:
                    # row é um dict (values())
                    for fname, mapping in entrada_maps.items():
                        if fname in row and row[fname] is not None:
                            row[fname] = mapping.get(str(row[fname]), row[fname])
        except Exception:
            pass

        estrutura_menu_item = EstruturaMenu.objects.filter(arquivo=menu_option).first()
        table_name = estrutura_menu_item.label if estrutura_menu_item else menu_option

        context = {
            'page_obj': page_obj,
            'headers': display_fields,
            'header_labels': campos_estrutura,
            'menu_option': menu_option,
            'table_name': table_name,
            'request': request,
            'target_input_id': request.GET.get('target_input_id', 'id_related_field')
        }

        # Detecta requisição HTMX pelo header HX-Request
        is_htmx = request.headers.get('HX-Request') == 'true'
        hx_target = request.headers.get('HX-Target', '')
        
        # Log para debug
        logger.info(f"[MODAL_GRID] is_htmx={is_htmx}, hx_target={hx_target}, page={request.GET.get('page', '1')}")
        
        # Se é requisição HTMX com target #grid-container, retorna apenas o partial
        if is_htmx and hx_target == 'grid-container':
            logger.info(f"[MODAL_GRID] Retornando grid_content.html para página {request.GET.get('page', '1')}")
            return render(request, 'app_rpps/partials/grid_content.html', context)
        
        # Caso contrário, retorna o modal completo
        logger.info(f"[MODAL_GRID] Retornando modal_grid.html completo")
        return render(request, 'app_rpps/modal_grid.html', context)

    except Exception as e:
        logger.error('--- DEBUG: Exception em modal_grid_view: ---', exc_info=True)
        return HttpResponse(str(e), status=500)


# ========== MODAL DE PESQUISA DINÂMICA GENÉRICO ==========
@login_required
def modal_search_view(request, tabela):
    """
    View genérica para modal de pesquisa dinâmica.
    Lê RppsEstrutura para montar filtros e grid automaticamente.
    
    Funcionalidades:
    - Filtros dinâmicos baseados em unique_together
    - Grid com seleção única (radio button)
    - Botões: Transferir, Relatório, Excel, Retornar
    - Suporta pesquisa na tabela principal OU em tabelas FK
    """
    try:
        # Verifica se é pesquisa em tabela FK ou tabela principal
        is_fk_search = request.GET.get('fk_search', 'false') == 'true'
        parent_table = request.GET.get('parent_table', tabela)
        
        # Busca o modelo
        model = MODEL_MAPPING.get(tabela)
        if not model:
            return HttpResponse(f"Modelo '{tabela}' não encontrado", status=404)
        
        # Busca estrutura do menu
        estrutura_menu = EstruturaMenu.objects.filter(arquivo=tabela).first()
        table_name = estrutura_menu.label if estrutura_menu else tabela
        
        # Busca campos da estrutura
        estruturas = RppsEstrutura.objects.filter(nome_tabela=tabela).order_by('ordem_campo')
        
        # Identifica campos do unique_together para filtros
        filter_fields = []
        unique_constraints = getattr(model._meta, 'unique_together', [])
        
        if unique_constraints:
            if isinstance(unique_constraints, (list, tuple)) and len(unique_constraints) > 0:
                unique_fields = unique_constraints[0] if isinstance(unique_constraints[0], (list, tuple)) else unique_constraints
                filter_fields = list(unique_fields)
        
        # Fallback: se não tem unique_together, usa primeiros 5 campos
        if not filter_fields:
            filter_fields = [e.nome_campo for e in estruturas[:5] if e.nome_campo != 'id']
        
        # Monta configuração dos filtros
        filter_configs = []
        for field_name in filter_fields:
            campo_estrutura = estruturas.filter(nome_campo=field_name).first()
            if campo_estrutura:
                filter_config = {
                    'name': field_name,
                    'label': campo_estrutura.label_campo,
                    'type': campo_estrutura.tipo_campo,
                    'options': None,
                    'is_cpf_cnpj': False,  # Flag para CPF/CNPJ
                    'attrs': {
                        'class': 'form-control form-control-sm',
                        'id': f'filter_{field_name}',
                        'placeholder': f'Filtrar por {campo_estrutura.label_campo}'
                    }
                }
                
                # Select com entrada_espec
                if campo_estrutura.entrada_espec:
                    filter_config['options'] = _parse_select_options_espec(campo_estrutura.entrada_espec)
                    filter_config['type'] = 'select'
                
                # Máscara CPF/CNPJ
                if campo_estrutura.tipo_campo.lower() == 'varchar5':
                    filter_config['is_cpf_cnpj'] = True
                    filter_config['attrs']['maxlength'] = 18
                
                filter_configs.append(filter_config)
        
        # Aplica filtros na queryset
        queryset = model.objects.all()
        active_filters = {}
        
        # NOVA: Pesquisa genérica inteligente (parâmetro 'search')
        search_query = request.GET.get('search', '').strip()
        sort_field = request.GET.get('sort_field', '').strip()
        
        if search_query:
            # Se há coluna ordenada, pesquisa apenas nela
            if sort_field and sort_field in [e.nome_campo for e in estruturas]:
                try:
                    campo_model = model._meta.get_field(sort_field)
                    campo_type = campo_model.get_internal_type()
                    
                    if campo_type in ['IntegerField', 'SmallIntegerField', 'BigIntegerField']:
                        # Campo numérico: igualdade exata
                        try:
                            search_int = int(search_query)
                            queryset = queryset.filter(**{sort_field: search_int})
                        except ValueError:
                            pass  # Se não for número, ignora
                    else:
                        # Campo texto: contém (case-insensitive)
                        queryset = queryset.filter(**{f'{sort_field}__icontains': search_query})
                    
                    active_filters['search'] = f'{search_query} (em {sort_field})'
                except Exception as e:
                    logger.error(f"[MODAL_SEARCH] Erro ao pesquisar em {sort_field}: {e}")
            else:
                # Sem ordenação: pesquisa em TODOS os campos de texto
                from django.db.models import Q
                q_filters = Q()
                
                for campo in estruturas:
                    try:
                        campo_model = model._meta.get_field(campo.nome_campo)
                        campo_type = campo_model.get_internal_type()
                        
                        # Apenas campos de texto
                        if campo_type in ['CharField', 'TextField']:
                            q_filters |= Q(**{f'{campo.nome_campo}__icontains': search_query})
                    except:
                        continue
                
                if q_filters:
                    queryset = queryset.filter(q_filters)
                    active_filters['search'] = f'{search_query} (em todos os campos)'
        
        # Filtros específicos por campo (mantidos para compatibilidade)
        for field_name in filter_fields:
            filter_value = request.GET.get(field_name, '').strip()
            
            # Ignora valores vazios, "0" ou "null"
            if not filter_value or filter_value in ['0', 'null', 'NULL', 'None']:
                continue
            
            # Remove máscara CPF/CNPJ
            campo_estrutura = estruturas.filter(nome_campo=field_name).first()
            if campo_estrutura and campo_estrutura.tipo_campo.lower() == 'varchar5':
                filter_value = re.sub(r'\D', '', filter_value)
            
            # Aplica filtro
            try:
                campo_model = model._meta.get_field(field_name)
                campo_type = campo_model.get_internal_type()
                
                if campo_type == 'ForeignKey':
                    # ForeignKey: busca no campo relacionado
                    filter_lookup = f'{field_name}__CpfCnpj__icontains'
                    queryset = queryset.filter(**{filter_lookup: filter_value})
                elif campo_type in ['IntegerField', 'SmallIntegerField', 'BigIntegerField', 'PositiveIntegerField', 'PositiveSmallIntegerField']:
                    # Campo inteiro: usa igualdade exata
                    try:
                        filter_value_int = int(filter_value)
                        queryset = queryset.filter(**{field_name: filter_value_int})
                    except ValueError:
                        continue
                else:
                    # Campo texto: usa icontains
                    filter_lookup = f'{field_name}__icontains'
                    queryset = queryset.filter(**{filter_lookup: filter_value})
                
                active_filters[field_name] = filter_value
            except Exception as e:
                logger.error(f"[MODAL_SEARCH] Erro ao aplicar filtro {field_name}: {e}")
        
        # Adiciona valores ativos em cada filter_config (evita usar get_item no template)
        for filter_config in filter_configs:
            filter_config['active_value'] = active_filters.get(filter_config['name'], '')
        
        # Define campos para exibir na grid exclusivamente pela estrutura do metadado
        display_fields = [campo.nome_campo for campo in estruturas if campo.nome_campo]

        # FALLBACK técnico somente quando não existe configuração em RppsEstrutura
        if not display_fields:
            for field in model._meta.fields:
                if not field.name.endswith('_id') and field.name not in ['id', 'created_at', 'updated_at']:
                    display_fields.append(field.name)

            if not display_fields:
                display_fields.append(model._meta.pk.name)
        
        # Ordenação dinâmica (suporta sort_field e sort_dir)
        pk_field = model._meta.pk.name
        sort_field = request.GET.get('sort_field', '').strip()  # Remove espaços extras
        sort_dir = request.GET.get('sort_dir', 'desc').strip()
        
        if sort_field and sort_field in display_fields:
            # Aplica ordenação pelo campo solicitado
            order_prefix = '-' if sort_dir == 'desc' else ''
            try:
                queryset = queryset.order_by(f'{order_prefix}{sort_field}')
            except:
                # Fallback para ordenação pela PK
                queryset = queryset.order_by(f'-{pk_field}')
        else:
            # Ordenação padrão pela PK
            try:
                queryset = queryset.order_by(f'-{pk_field}')
            except:
                queryset = queryset.order_by()
        
        paginator = Paginator(queryset, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        # Formata valores da grid
        grid_data = []
        for obj in page_obj:
            row_values = []
            for field_name in display_fields:
                try:
                    value = getattr(obj, field_name)
                    
                    # Formata ForeignKeys
                    if hasattr(value, 'CpfCnpj'):
                        value = aplicar_mascara_documento(value.CpfCnpj)
                    
                    # Formata datas
                    elif isinstance(value, (datetime.date, datetime.datetime)):
                        value = value.strftime('%d/%m/%Y')
                    
                    # Formata decimais
                    elif isinstance(value, decimal.Decimal):
                        value = f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                    
                    # Substitui por descrição de entrada_espec
                    campo_estrutura = estruturas.filter(nome_campo=field_name).first()
                    if campo_estrutura and campo_estrutura.entrada_espec:
                        mapping = _parse_select_options_espec(campo_estrutura.entrada_espec)
                        value = mapping.get(str(value), value)
                    
                    row_values.append(value if value is not None else '')
                except Exception as e:
                    row_values.append('')
                    logger.error(f"Erro ao formatar campo {field_name}: {e}")
            
            # Usa a chave primária correta (pode ser 'id', 'CpfCnpj', etc)
            pk_value = getattr(obj, pk_field)
            grid_data.append({'id': pk_value, 'values': row_values})
        
        # Monta labels
        field_labels_dict = {c.nome_campo: c.label_campo for c in estruturas if c.nome_campo in display_fields}
        
        # FALLBACK: Se campo não tem label em estrutura, usa verbose_name do modelo ou o próprio nome
        for field_name in display_fields:
            if field_name not in field_labels_dict:
                try:
                    model_field = model._meta.get_field(field_name)
                    field_labels_dict[field_name] = model_field.verbose_name or field_name.replace('_', ' ').title()
                except:
                    field_labels_dict[field_name] = field_name.replace('_', ' ').title()
        
        ordered_labels = [field_labels_dict.get(f, f) for f in display_fields]
        
        # Monta lista com (nome_campo, label) para ordenação
        field_headers = [{'name': field, 'label': field_labels_dict.get(field, field)} for field in display_fields]
        
        # Contexto
        context = {
            'tabela': tabela,
            'table_name': table_name,
            'parent_table': parent_table,
            'is_fk_search': is_fk_search,
            'filter_configs': filter_configs,
            'active_filters': active_filters,
            'ordered_labels': ordered_labels,
            'field_headers': field_headers,  # NOVO: para ordenação
            'grid_data': grid_data,
            'page_obj': page_obj,
            'request': request,
        }
        
        # Se é HTMX, retorna apenas a grid
        is_htmx_request = request.headers.get('HX-Request')
        htmx_target = request.headers.get('HX-Target', '')
        
        if is_htmx_request and htmx_target == 'search-grid-container':
            return render(request, 'app_rpps/partials/search_grid_content.html', context)
        
        # Retorna modal completo
        return render(request, 'app_rpps/modal_search.html', context)
        
    except Exception as e:
        logger.error(f'Erro em modal_search_view para tabela {tabela}: {e}', exc_info=True)
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f'Traceback completo: {error_detail}')
        return HttpResponse(f"Erro ao carregar pesquisa: {str(e)}", status=500)
