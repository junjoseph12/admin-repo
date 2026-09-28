# web/models.py
from django.db import models


# ============================================================
# All models below use managed = False because these tables
# already exist in Supabase — Django should never try to create,
# alter, or drop them via migrations. They just describe the
# existing schema so the ORM can query it.
#
# Verified directly against your live Supabase project
# (Capstone_Pack-N-Ship, ref: ellqwkalvvedtyivdozd) — column
# names/types match exactly what's really there, not just the
# paper ERD.
# ============================================================


class User(models.Model):
    user_id = models.BigAutoField(primary_key=True)
    auth_id = models.UUIDField(null=True, blank=True)  # FK to auth.users(id) — Supabase Auth
    first_name = models.CharField(max_length=255)
    middle_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=50, null=True, blank=True)
    profile_photo = models.CharField(max_length=255, null=True, blank=True)
    id_photo = models.CharField(max_length=255, null=True, blank=True)
    valid_id_type = models.CharField(max_length=100, null=True, blank=True)
    valid_id_number = models.CharField(max_length=100, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    primary_loc_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'users'

    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return ' '.join(p for p in parts if p)

    def __str__(self):
        return self.full_name()


class Location(models.Model):
    location_id = models.BigAutoField(primary_key=True)
    street_address = models.CharField(max_length=255)
    barangay = models.CharField(max_length=255)
    city = models.CharField(max_length=255)
    province = models.CharField(max_length=255)
    zip_code = models.CharField(max_length=20)
    latitude = models.DecimalField(max_digits=10, decimal_places=6)
    longitude = models.DecimalField(max_digits=10, decimal_places=6)

    class Meta:
        managed = False
        db_table = 'locations'

    def full_address(self):
        return f"{self.street_address}, {self.barangay}, {self.city}, {self.province}"

    def __str__(self):
        return self.full_address()


class Receiver(models.Model):
    receiver_id = models.BigAutoField(primary_key=True)
    sender = models.ForeignKey(User, db_column='sender_id', on_delete=models.DO_NOTHING, related_name='receivers')
    receiver_name = models.CharField(max_length=255)
    receiver_phone = models.CharField(max_length=50)
    receiver_email = models.CharField(max_length=255, null=True, blank=True)
    is_favorite = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'receivers'

    def __str__(self):
        return self.receiver_name


class Vehicle(models.Model):
    vehicle_id = models.BigAutoField(primary_key=True)
    vehicle_type = models.CharField(max_length=100)
    plate_number = models.CharField(max_length=50)
    max_volume_liters = models.DecimalField(max_digits=10, decimal_places=2)
    max_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    cargo_length_cm = models.DecimalField(max_digits=10, decimal_places=2)
    cargo_width_cm = models.DecimalField(max_digits=10, decimal_places=2)
    cargo_height_cm = models.DecimalField(max_digits=10, decimal_places=2)
    vehicle_doc = models.CharField(max_length=255, null=True, blank=True)
    verification_status = models.CharField(max_length=50, default='Pending')
    provider = models.ForeignKey(User, db_column='provider_id', on_delete=models.DO_NOTHING, related_name='vehicles')
    rejection_reason = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'vehicles'

    def __str__(self):
        return f"{self.vehicle_type} · {self.plate_number}"


class CargoProfile(models.Model):
    cargo_id = models.BigAutoField(primary_key=True)
    description = models.TextField(null=True, blank=True)
    cargo_pic = models.CharField(max_length=255, null=True, blank=True)
    total_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    cargo_length_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cargo_width_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cargo_height_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    small_box_qty = models.IntegerField(default=0)
    medium_box_qty = models.IntegerField(default=0)
    large_box_qty = models.IntegerField(default=0)
    is_fragile = models.BooleanField(default=False)
    sender = models.ForeignKey(User, db_column='sender_id', on_delete=models.DO_NOTHING, related_name='cargo_profiles')

    class Meta:
        managed = False
        db_table = 'cargo_profiles'

    def dimensions_label(self):
        if self.cargo_length_cm and self.cargo_width_cm and self.cargo_height_cm:
            return f"{self.cargo_length_cm} x {self.cargo_width_cm} x {self.cargo_height_cm} cm"
        return '—'

    def __str__(self):
        return self.description or f"Cargo #{self.cargo_id}"


class DeliveryRequest(models.Model):
    request_id = models.BigAutoField(primary_key=True)
    pickup_type = models.CharField(max_length=50)  # 'Curb-side' | 'Door-to-Door'
    scheduled_time = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(max_length=50, default='Pending')
    emergency_flag = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    receiver_phone = models.CharField(max_length=50)
    total_distance = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=2)
    dropoff_location = models.ForeignKey(Location, db_column='dropoff_location_id', on_delete=models.DO_NOTHING, related_name='dropoff_requests')
    pickup_location = models.ForeignKey(Location, db_column='pickup_location_id', on_delete=models.DO_NOTHING, related_name='pickup_requests')
    rate_id = models.BigIntegerField()  # not modeled yet — not needed for deliveries.html
    sender = models.ForeignKey(User, db_column='sender_id', on_delete=models.DO_NOTHING, related_name='delivery_requests')
    cargo = models.ForeignKey(CargoProfile, db_column='cargo_id', on_delete=models.DO_NOTHING, related_name='delivery_requests')
    receiver = models.ForeignKey(Receiver, db_column='receiver_id', null=True, blank=True, on_delete=models.DO_NOTHING, related_name='delivery_requests')

    class Meta:
        managed = False
        db_table = 'delivery_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Request #{self.request_id} ({self.delivery_status})"


class Delivery(models.Model):
    delivery_id = models.BigAutoField(primary_key=True)
    accepted_at = models.DateTimeField(auto_now_add=True)
    estimated_eta = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    request = models.OneToOneField(DeliveryRequest, db_column='request_id', on_delete=models.DO_NOTHING, related_name='delivery')
    provider = models.ForeignKey(User, db_column='provider_id', on_delete=models.DO_NOTHING, related_name='deliveries_provided')
    route_id = models.BigIntegerField(null=True, blank=True)  # not modeled yet
    vehicle = models.ForeignKey(Vehicle, db_column='vehicle_id', on_delete=models.DO_NOTHING, related_name='deliveries')

    class Meta:
        managed = False
        db_table = 'deliveries'

    def __str__(self):
        return f"Delivery #{self.delivery_id}"


class EscrowPayment(models.Model):
    escrow_id = models.BigAutoField(primary_key=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    escrow_status = models.CharField(max_length=50, default='On hold')
    emergency_frozen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    bc_escrow_tx_hash = models.CharField(max_length=255, null=True, blank=True)
    delivery = models.OneToOneField(Delivery, db_column='delivery_id', on_delete=models.DO_NOTHING, related_name='escrow_payment')
    sender = models.ForeignKey(User, db_column='sender_id', on_delete=models.DO_NOTHING, related_name='escrow_payments_sent')
    provider = models.ForeignKey(User, db_column='provider_id', on_delete=models.DO_NOTHING, related_name='escrow_payments_received')

    class Meta:
        managed = False
        db_table = 'escrow_payments'

    def __str__(self):
        return f"Escrow #{self.escrow_id} ({self.escrow_status})"


class Transaction(models.Model):
    transaction_id = models.BigAutoField(primary_key=True)
    base_amount = models.DecimalField(max_digits=10, decimal_places=2)
    service_fee = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    penalty_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=100)
    status = models.CharField(max_length=50, default='Pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    escrow = models.OneToOneField(EscrowPayment, db_column='escrow_id', on_delete=models.DO_NOTHING, related_name='transaction')

    class Meta:
        managed = False
        db_table = 'transactions'
        # NOTE: unlike escrow_payments/qr_verifications/provider_verifications/
        # ratings_reviews, this table has NO bc_..._tx_hash column in the real
        # schema. If you want transaction-level blockchain anchoring later,
        # that's a column you'd need to add — it doesn't exist yet.

    def __str__(self):
        return f"Transaction #{self.transaction_id}"


class QRVerification(models.Model):
    qr_id = models.BigAutoField(primary_key=True)
    pickup_qr = models.CharField(max_length=255)
    dropoff_qr = models.CharField(max_length=255)
    pickup_pin = models.CharField(max_length=20)
    dropoff_pin = models.CharField(max_length=20)
    pickup_verified = models.BooleanField(default=False)
    dropoff_verified = models.BooleanField(default=False)
    bc_pickup_tx_hash = models.CharField(max_length=255, null=True, blank=True)
    bc_dropoff_tx_hash = models.CharField(max_length=255, null=True, blank=True)
    delivery = models.OneToOneField(Delivery, db_column='delivery_id', on_delete=models.DO_NOTHING, related_name='qr_verification')

    class Meta:
        managed = False
        db_table = 'qr_verifications'

    def __str__(self):
        return f"QR Verification for Delivery #{self.delivery_id}"


class DeliveryIssue(models.Model):
    issue_id = models.BigAutoField(primary_key=True)
    delivery = models.ForeignKey(Delivery, db_column='delivery_id', on_delete=models.DO_NOTHING, related_name='issues')
    reported_by = models.ForeignKey(User, db_column='reported_by', on_delete=models.DO_NOTHING, related_name='reported_issues')
    issue_type = models.CharField(max_length=100)
    description = models.TextField()
    status = models.CharField(max_length=50)  # 'Open' | 'Investigating' | 'Resolved'
    resolution = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'delivery_issues'
        ordering = ['-created_at']

    def __str__(self):
        return f"Issue #{self.issue_id} ({self.status})"


class ChatRoom(models.Model):
    room_id = models.BigAutoField(primary_key=True)
    delivery = models.OneToOneField(Delivery, db_column='delivery_id', on_delete=models.DO_NOTHING, related_name='chat_room')

    class Meta:
        managed = False
        db_table = 'chat_rooms'

    def __str__(self):
        return f"Chat Room #{self.room_id}"


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

class DeliveryStatusHistory(models.Model):
    status_id = models.BigAutoField(primary_key=True)
    delivery = models.ForeignKey(
        Delivery, db_column='delivery_id',
        on_delete=models.DO_NOTHING, related_name='status_history',
    )
    status = models.CharField(max_length=100)
    updated_at = models.DateTimeField()
 
    class Meta:
        managed = False
        db_table = 'delivery_status_history'
        ordering = ['updated_at']
 
    def __str__(self):
        return f"{self.status} @ {self.updated_at}"