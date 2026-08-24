from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='app_rpps/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.menu_view, name='menu'),
    path('relatorio/<str:tabela>/', views.report_view, name='report'),
    path('modal-grid/<str:menu_option>/', views.modal_grid_view, name='modal_grid'),
    path('modal-search/<str:tabela>/', views.modal_search_view, name='modal_search'),
    path('export/excel/<str:tabela>/', views.export_excel_view, name='export_excel'),
    path('export/pdf/<str:tabela>/', views.export_pdf_view, name='export_pdf'),
    path('api/related-fields/<str:tabela>/<str:campo_fk>/', views.get_related_fields_data, name='get_related_fields'),
    path('RPPS/', views.rpps_list_view, name='rpps_list_view'),
    path('<str:tabela>/check-fk/<str:campo_fk>/', views.check_fk_field, name='check_fk_field'),
    path('<str:tabela>/', views.dynamic_form_view, name='dynamic_form'),
    path('<str:tabela>/check/', views.check_record, name='check_record'),
    path('<str:tabela>/gerar-xml/', views.gerar_xml_view, name='gerar_xml'),  
    path('<str:tabela>/referencia/<str:campo_ref>/', views.load_referencia, name='load_referencia'),
    path('<str:tabela>/read/<int:record_id>/', views.read_record, name='read_record'),
    path('tratamento/<str:tabela>/', views.tratamento_record, name='tratamento_record'),
    path('tratamento/<str:tabela>/<int:record_id>/', views.tratamento_record, name='tratamento_record'),
]