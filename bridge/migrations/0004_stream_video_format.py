from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bridge', '0003_call_ended_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='stream',
            name='video_format',
            field=models.JSONField(blank=True, help_text='Where a video frame\'s pixels are (axes, shape, calibration, reference); null when not declared', null=True),
        ),
    ]
