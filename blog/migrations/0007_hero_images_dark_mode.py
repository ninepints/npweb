# Generated by Django 2.2.9 on 2020-01-19 04:48

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('wagtailimages', '0001_squashed_0021'),
        ('blog', '0006_new_pygments_lang_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='heroimage',
            name='svg_image_dark',
            field=models.FileField(blank=True, help_text='Alternative SVG image to display in dark mode.', upload_to='hero_images/', validators=[django.core.validators.FileExtensionValidator(['svg'])], verbose_name='dark SVG image'),
        ),
        migrations.AddField(
            model_name='heroimage',
            name='text_color',
            field=models.CharField(choices=[('light', 'Light text'), ('dark', 'Dark text'), ('either', 'Either color ok')], default='light', help_text='The color to use for overlaid text, to ensure contrast.', max_length=6),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='heroimage',
            name='wagtail_image_dark',
            field=models.ForeignKey(blank=True, help_text='Alternative Wagtail image to display in dark mode.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='wagtailimages.Image', verbose_name='dark Wagtail image'),
        ),
        migrations.AlterField(
            model_name='heroimage',
            name='svg_image',
            field=models.FileField(blank=True, upload_to='hero_images/', validators=[django.core.validators.FileExtensionValidator(['svg'])], verbose_name='SVG image'),
        ),
        migrations.AlterField(
            model_name='heroimage',
            name='wagtail_image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='wagtailimages.Image', verbose_name='Wagtail image'),
        ),
    ]
