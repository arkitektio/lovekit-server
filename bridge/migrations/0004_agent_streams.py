# Broadcasts give way to agents and the streams they declare. The new Stream is a different
# table in all but name, so the old models are dropped and the new ones created fresh instead
# of the old Stream being altered into one (no default could fill its agent).

import django.contrib.postgres.indexes
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentikate', '0007_user_profile'),
        ('bridge', '0003_callinvite'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name='Stream'),
        migrations.DeleteModel(name='SoloBroadcast'),
        migrations.DeleteModel(name='CollaborativeBroadcast'),
        migrations.DeleteModel(name='Broadcast'),
        migrations.DeleteModel(name='Streamer'),
        migrations.CreateModel(
            name='Agent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='When this agent first declared its streams')),
                ('client', models.ForeignKey(help_text='The client (app instance) this agent runs as', on_delete=django.db.models.deletion.CASCADE, related_name='lovekit_agents', to='authentikate.client')),
                ('organization', models.ForeignKey(help_text="The organization whose members may watch this agent's streams", on_delete=django.db.models.deletion.CASCADE, related_name='lovekit_agents', to='authentikate.organization')),
                ('user', models.ForeignKey(help_text='The user this agent runs for', on_delete=django.db.models.deletion.CASCADE, related_name='lovekit_agents', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Stream',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stored_descriptors', models.JSONField(blank=True, db_default=models.Value({}, output_field=models.JSONField()), default=dict, help_text='The descriptors of this object, as its structure declares them: stored on every save so that a `requires` filter reads them in SQL')),
                ('key', models.CharField(help_text="The agent's name for this stream, stable across restarts; the name of its LiveKit track", max_length=200)),
                ('title', models.CharField(help_text='What the stream is called', max_length=1000)),
                ('kind', models.CharField(choices=[('video', 'VIDEO'), ('audio', 'AUDIO')], help_text='Whether this is video or audio', max_length=50)),
                ('description', models.TextField(blank=True, help_text='What the stream shows', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='When the agent first declared this stream')),
                ('agent', models.ForeignKey(help_text='The agent that declared this stream', on_delete=django.db.models.deletion.CASCADE, related_name='streams', to='bridge.agent')),
            ],
        ),
        migrations.AddConstraint(
            model_name='agent',
            constraint=models.UniqueConstraint(fields=('client', 'user', 'organization'), name='one_agent_per_client_user_org'),
        ),
        migrations.AddIndex(
            model_name='stream',
            index=django.contrib.postgres.indexes.GinIndex(fields=['stored_descriptors'], name='bridge_stream_desc_gin', opclasses=['jsonb_path_ops']),
        ),
        migrations.AddConstraint(
            model_name='stream',
            constraint=models.UniqueConstraint(fields=('agent', 'key'), name='one_stream_per_agent_key'),
        ),
    ]
