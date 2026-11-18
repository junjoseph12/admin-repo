# web/models.py
from django.db import models


class ProviderVerification(models.Model):
    verification_id = models.BigAutoField(primary_key=True)
    drivers_license_number = models.CharField(max_length=255, unique=True)
    license_expiry_date = models.DateField()
    selfie_photo = models.CharField(max_length=255)
    verification_status = models.CharField(max_length=50, default='Pending')
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    bc_verif_tx_hash = models.CharField(max_length=255, null=True, blank=True)
    admin_id = models.BigIntegerField(null=True, blank=True)
    provider_id = models.BigIntegerField()

    class Meta:
        managed = False                    # Table already exists in Supabase
        db_table = 'provider_verifications'
        ordering = ['-submitted_at']

    def __str__(self):
        return f"Verification #{self.verification_id}"