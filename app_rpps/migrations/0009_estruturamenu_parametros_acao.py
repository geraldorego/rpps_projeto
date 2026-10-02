from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_rpps', '0008_fix_referencia_config_to_textfield'),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE [dbo].[EstruturaMenu] ADD [parametros_acao] NVARCHAR(MAX) NULL',
            reverse_sql='ALTER TABLE [dbo].[EstruturaMenu] DROP COLUMN [parametros_acao]',
        ),
        migrations.AddField(
            model_name='estruturamenu',
            name='parametros_acao',
            field=models.TextField(
                blank=True,
                help_text='Configuração JSON opcional para ações como CRUD-C.',
                null=True,
                verbose_name='Parâmetros da ação',
            ),
        ),
        migrations.AlterField(
            model_name='estruturamenu',
            name='acao',
            field=models.CharField(
                choices=[
                    ('CRUD', 'Formulário CRUD'),
                    ('CRUD-C', 'Formulário CRUD com cópia'),
                    ('BOTAO', 'Ação com Botão'),
                    ('RELATORIO', 'Relatório'),
                    ('LINK', 'Link Externo'),
                ],
                default='CRUD',
                max_length=50,
                verbose_name='Tipo de Ação',
            ),
        ),
    ]