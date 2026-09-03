from django.conf import settings
from django.db import migrations, models


def copy_existing_engineer_assignments(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    for project in Project.objects.exclude(site_engineer_id=None).iterator():
        project.site_engineers.add(project.site_engineer_id)


def restore_single_engineer_assignments(apps, schema_editor):
    Project = apps.get_model('projects', 'Project')
    for project in Project.objects.all().iterator():
        engineer = project.site_engineers.order_by('pk').first()
        project.site_engineer_id = engineer.pk if engineer else None
        project.save(update_fields=['site_engineer'])


class Migration(migrations.Migration):
    dependencies = [
        ('projects', '0003_project_site_engineer'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='site_engineers',
            field=models.ManyToManyField(
                blank=True,
                related_name='assigned_projects',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            copy_existing_engineer_assignments,
            restore_single_engineer_assignments,
        ),
        migrations.RemoveField(
            model_name='project',
            name='site_engineer',
        ),
    ]
