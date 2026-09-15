from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        REGULAR = "regular", "Regular User"
        ADVISOR = "advisor", "Financial Advisor"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.REGULAR)
    advisor = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clients",
        limit_choices_to={"role": Role.ADVISOR},
    )

    def __str__(self):
        return self.username
