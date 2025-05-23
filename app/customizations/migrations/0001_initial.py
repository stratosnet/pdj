# Generated by Django 5.1.7 on 2025-04-18 11:16

import tinymce.models
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('admin_interface', '0030_theme_collapsible_stacked_inlines_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailTemplate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('type', models.CharField(choices=[('base', 'base'), ('payment_success', 'payment_success'), ('subscription_canceled', 'subscription_canceled'), ('subscription_renewal', 'subscription_renewal')], max_length=64, verbose_name='type')),
                ('subject', models.TextField(max_length=988, verbose_name='subject')),
                ('content', tinymce.models.HTMLField(verbose_name='content')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
            ],
            options={
                'verbose_name': 'email template',
                'verbose_name_plural': 'email templates',
                'ordering': ['type'],
            },
        ),
        migrations.CreateModel(
            name='Theme',
            fields=[
            ],
            options={
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('admin_interface.theme',),
        ),
    ]
