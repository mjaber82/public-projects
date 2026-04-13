import uuid

from django.db import models


class BaseModel(models.Model):
    public_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_dt = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_dt = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
