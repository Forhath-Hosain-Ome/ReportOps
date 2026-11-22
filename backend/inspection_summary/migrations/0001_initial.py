import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='InspectionSummaryJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('PROCESSING', 'Processing'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], db_index=True, default='PENDING', max_length=20)),
                ('stage', models.CharField(blank=True, max_length=64)),
                ('inspection_summary_name', models.CharField(max_length=255)),
                ('raw_name', models.CharField(max_length=255)),
                ('inspection_summary_path', models.CharField(max_length=512)),
                ('raw_path', models.CharField(max_length=512)),
                ('output_path', models.CharField(blank=True, max_length=512)),
                ('inspection_summary_sha256', models.CharField(max_length=64)),
                ('raw_sha256', models.CharField(max_length=64)),
                ('sheet_manifest', models.JSONField(default=list)),
                ('error_code', models.CharField(blank=True, max_length=64)),
                ('error_detail', models.JSONField(default=dict)),
                ('task_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('run_token', models.UUIDField(blank=True, null=True)),
                ('dispatch_generation', models.PositiveIntegerField(default=1)),
                ('dispatch_token', models.UUIDField(default=uuid.uuid4)),
                ('dispatch_state', models.CharField(choices=[('REQUESTED', 'Requested'), ('PUBLISHING', 'Publishing'), ('QUEUED', 'Queued'), ('UNKNOWN', 'Unknown'), ('PROCESSING', 'Processing'), ('TERMINAL', 'Terminal')], default='REQUESTED', max_length=20)),
                ('publication_lease_expires_at', models.DateTimeField(blank=True, null=True)),
                ('last_error_code', models.CharField(blank=True, max_length=64)),
                ('maintenance_token', models.UUIDField(blank=True, null=True)),
                ('maintenance_started_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('processing_started_at', models.DateTimeField(blank=True, null=True)),
                ('processing_lease_expires_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('processing_finished_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('input_deleted_at', models.DateTimeField(blank=True, null=True)),
                ('output_deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inspection_summary_jobs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['created_by', '-created_at'], name='insp_sum_owner_created'), models.Index(fields=['status', 'expires_at'], name='insp_sum_status_expiry')],
            },
        ),
    ]
