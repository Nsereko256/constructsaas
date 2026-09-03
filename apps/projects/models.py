from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Company, User


class Project(models.Model):
    STATUS_PLANNING = 'planning'
    STATUS_ACTIVE = 'active'
    STATUS_ON_HOLD = 'on_hold'
    STATUS_COMPLETED = 'completed'

    STATUS_CHOICES = [
        (STATUS_PLANNING, 'Planning'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_ON_HOLD, 'On Hold'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    client = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNING)
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_projects',
    )
    site_engineers = models.ManyToManyField(
        User,
        blank=True,
        related_name='assigned_projects',
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = (
            ('company', 'name'),
            ('company', 'code'),
        )

    def __str__(self):
        return f'{self.name} ({self.code})'

    def get_absolute_url(self):
        return f'/api/projects/{self.pk}/'


class ProjectSite(models.Model):
    """A physical work location under a project, independent of its store."""
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_ON_HOLD = 'ON_HOLD'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_CHOICES = [(STATUS_ACTIVE, 'Active'), (STATUS_ON_HOLD, 'On hold'), (STATUS_COMPLETED, 'Completed')]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=180)
    code = models.CharField(max_length=40)
    location = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_project_sites')
    site_engineers = models.ManyToManyField(User, blank=True, related_name='assigned_project_sites')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_project_sites')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['project__name', 'name']
        constraints = [models.UniqueConstraint(fields=['project', 'code'], name='unique_project_site_code')]

    def clean(self):
        if self.manager_id and self.manager.company_id != self.project.company_id:
            raise ValueError('Site manager must belong to the project company.')

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.project.code} · {self.name}'


class ProjectGoal(models.Model):
    """A measurable project milestone, optionally owned by one physical site."""
    STATUS_NOT_STARTED = 'NOT_STARTED'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_ON_HOLD = 'ON_HOLD'
    STATUS_CHOICES = [
        (STATUS_NOT_STARTED, 'Not started'),
        (STATUS_IN_PROGRESS, 'In progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_ON_HOLD, 'On hold'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='goals')
    site = models.ForeignKey(ProjectSite, on_delete=models.SET_NULL, null=True, blank=True, related_name='goals')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    completion_percent = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='completed_project_goals')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', 'title']

    def clean(self):
        if self.site_id and self.site.project_id != self.project_id:
            raise ValueError('A goal site must belong to the selected project.')
        if self.completion_percent > 100:
            raise ValueError('Goal completion cannot exceed 100 percent.')
        if self.weight <= 0:
            raise ValueError('Goal weight must be greater than zero.')


class ProjectStaffAssignment(models.Model):
    ROLE_MANAGER = 'MANAGER'
    ROLE_ENGINEER = 'ENGINEER'
    ROLE_SITE_CONTACT = 'SITE_CONTACT'
    ROLE_CHOICES = [(ROLE_MANAGER, 'Project manager'), (ROLE_ENGINEER, 'Site engineer'), (ROLE_SITE_CONTACT, 'Site contact')]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='staff_assignments')
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='project_staff_assignments')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_primary_contact = models.BooleanField(default=False)
    allocation_percent = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['role', '-is_primary_contact', 'user__username']
        constraints = [models.UniqueConstraint(fields=['project', 'user', 'role'], name='unique_project_staff_role')]

    def clean(self):
        if self.user_id and self.user.company_id != self.project.company_id:
            raise ValueError('Project staff must belong to the project company.')
        if self.allocation_percent < 0 or self.allocation_percent > 100:
            raise ValueError('Allocation must be between 0 and 100.')
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError('Assignment end date cannot be before start date.')


class ApprovalDelegation(models.Model):
    delegator = models.ForeignKey(User, on_delete=models.PROTECT, related_name='delegations_given')
    delegate = models.ForeignKey(User, on_delete=models.PROTECT, related_name='delegations_received')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='approval_delegations')
    effective_from = models.DateField()
    effective_to = models.DateField()
    reason = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-effective_from', '-created_at']

    def clean(self):
        if self.delegator_id and self.delegate_id and self.delegator.company_id != self.delegate.company_id:
            raise ValueError('Delegation users must belong to the same company.')
        if self.delegator_id == self.delegate_id:
            raise ValueError('A user cannot delegate to themselves.')
        if self.effective_to < self.effective_from:
            raise ValueError('Delegation end date cannot be before its start date.')


class ChatRoom(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='project_chat_rooms')
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='chat_room')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['project__name']

    def __str__(self):
        return f'Chat room for {self.project.name}'


class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_chat_messages',
    )
    content = models.TextField()
    is_system_message = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        sender = 'System' if self.is_system_message else self.sender or 'Unknown sender'
        return f'{sender}: {self.content[:50]}'


@receiver(post_save, sender=Project)
def create_project_chat_room(sender, instance, created, **kwargs):
    if created:
        ChatRoom.objects.get_or_create(
            project=instance,
            defaults={'company': instance.company},
        )
