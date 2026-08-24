import csv
import io

from django.http import HttpResponse
from openpyxl import Workbook


def exportar_csv(queryset, campos):
    """Exporta um queryset para CSV usando apenas os campos informados."""
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(list(campos))

    for row in queryset.values_list(*campos):
        writer.writerow(list(row))

    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="exportacao.csv"'
    return response


def exportar_excel(queryset, campos):
    """Exporta um queryset para Excel usando apenas os campos informados."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Relatório'
    sheet.append(list(campos))

    for row in queryset.values_list(*campos):
        sheet.append(list(row))

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="exportacao.xlsx"'
    return response
