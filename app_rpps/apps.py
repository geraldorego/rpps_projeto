# app_rpps/apps.py
from django.apps import AppConfig

class AppRppsConfig(AppConfig):
    name = 'app_rpps'
    verbose_name = 'RPPS'

    def ready(self):
        # Certifique-se de que os modelos estão sendo carregados
        from .models import ResultadoAtuarial