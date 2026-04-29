from django.db import models

class Notification(models.Model):
    recipient_id = models.IntegerField(help_text="ID of the user from the auth service")
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for User {self.recipient_id}: {self.title}"
