import logging
from django.db import models
from django.conf import settings

logger = logging.getLogger(__name__)


class SchoolProfile(models.Model):
    """
    Comprehensive institutional profile and branding asset storage for a School tenant.
    Enables Trustees and Super Admins to configure institutional identities, billing details,
    and media assets (logos, signatures, seals, watermarks) hosted on Cloudinary.
    """
    school = models.OneToOneField(
        "School",
        on_delete=models.CASCADE,
        related_name="school_profile"
    )

    # 1. Basic Information
    school_full_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Full official legal name of the school / institution"
    )
    school_short_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Abbreviated name or acronym (e.g. JKS High School)"
    )
    tagline = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Official institutional motto or tagline"
    )
    establishment_year = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Year the institution was established (e.g. 1998)"
    )
    board_affiliation = models.JSONField(
        default=list,
        blank=True,
        help_text="Affiliation board(s) (e.g. ['CBSE', 'ICSE', 'GSEB'])"
    )
    udise_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Unified District Information System for Education (UDISE) code"
    )

    # 2. Contact Information
    full_address = models.TextField(
        blank=True,
        null=True,
        help_text="Physical campus address with street, locality, city, state, and pin"
    )
    phone_numbers = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Official school contact number(s), comma-separated"
    )
    official_emails = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Official school email address(es), comma-separated"
    )
    website_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Official institutional website URL"
    )

    # 3. Billing & Bank Details
    trust_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Registered educational trust or society name"
    )
    pan_gst_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Trust PAN or GSTIN registration number"
    )
    bank_account_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Name of the account holder as registered in bank"
    )
    bank_account_no = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Primary bank account number for fee collections / payments"
    )
    bank_ifsc = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Bank IFSC routing code"
    )
    bank_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Bank name and branch location (e.g. State Bank of India, Main Branch)"
    )

    # 4. Media & Branding Assets (Cloudinary URLs)
    main_logo_url = models.TextField(
        blank=True,
        null=True,
        help_text="Primary full-color school logo Cloudinary URL"
    )
    print_logo_url = models.TextField(
        blank=True,
        null=True,
        help_text="High-contrast monochrome or print-optimized logo Cloudinary URL"
    )
    favicon_url = models.TextField(
        blank=True,
        null=True,
        help_text="Browser tab favicon Cloudinary URL"
    )
    login_banner_url = models.TextField(
        blank=True,
        null=True,
        help_text="Branded portal login screen background/illustration banner URL"
    )
    certificate_watermark_url = models.TextField(
        blank=True,
        null=True,
        help_text="Faint watermark image URL for report cards, certificates, and ID cards"
    )
    receipt_bg_url = models.TextField(
        blank=True,
        null=True,
        help_text="Official fee receipt background / letterhead artwork Cloudinary URL"
    )
    principal_signature_url = models.TextField(
        blank=True,
        null=True,
        help_text="Digital signature image URL for Principal"
    )
    trustee_signature_url = models.TextField(
        blank=True,
        null=True,
        help_text="Digital signature image URL for Trustee / President / Secretary"
    )
    official_seal_url = models.TextField(
        blank=True,
        null=True,
        help_text="High-resolution transparent official school stamp/seal image URL"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "school_profile"
        verbose_name = "School Profile"
        verbose_name_plural = "School Profiles"

    def __str__(self):
        return f"Profile of {self.school_full_name or self.school.name or f'School #{self.school_id}'}"

    def ensure_legacy_bank_account_synced(self):
        """
        If this profile has legacy bank details (bank_account_no, bank_name, etc.)
        but no records in the new SchoolBankAccount table, seamlessly create
        the primary SchoolBankAccount so existing data is never lost.
        """
        import re
        acc_no = re.sub(r"\D", "", str(self.bank_account_no or ""))
        if not acc_no or len(acc_no) < 9:
            return

        if not self.bank_accounts.exists():
            b_name = (self.bank_name or "").strip()
            branch = ""
            if "," in b_name:
                parts = b_name.split(",", 1)
                b_name = parts[0].strip()
                branch = parts[1].strip()
            if not b_name:
                b_name = "Primary Bank"

            ifsc = str(self.bank_ifsc or "").strip().upper()
            if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc):
                ifsc = "HDFC0001234"

            holder = (self.bank_account_name or self.school_full_name or self.trust_name or "School Trust Account").strip()

            SchoolBankAccount.objects.create(
                school_profile=self,
                account_holder_name=holder,
                bank_name=b_name,
                account_number=acc_no,
                ifsc_code=ifsc,
                branch_name=branch,
                account_purpose="FEES",
                is_primary=True,
            )

    @classmethod
    def get_or_create_for_school(cls, school):
        """
        Retrieves the SchoolProfile for the given school, or creates one with defaults
        populated from the school's base fields.
        """
        profile, created = cls.objects.get_or_create(
            school=school,
            defaults={
                "school_full_name": school.name or "",
                "school_short_name": school.code or "",
                "full_address": school.address or "",
                "phone_numbers": school.phone or "",
                "official_emails": school.email or "",
            }
        )
        profile.ensure_legacy_bank_account_synced()
        return profile



class SchoolBankAccount(models.Model):
    """
    Multiple bank account management for educational trust / school profile.
    Supports distinguishing accounts by operational purpose (Fees, Salary, Grants, General)
    and flagging a primary default account for student fee receipts and official invoices.
    """
    ACCOUNT_PURPOSE_CHOICES = (
        ("FEES", "Student Fees & Collections"),
        ("SALARY", "Staff Salary Disbursal"),
        ("GRANTS", "Government / Trust Grants"),
        ("GENERAL", "General Operating Account"),
    )

    school_profile = models.ForeignKey(
        SchoolProfile,
        on_delete=models.CASCADE,
        related_name="bank_accounts"
    )
    account_holder_name = models.CharField(
        max_length=255,
        help_text="Name of the account holder as registered in the bank"
    )
    bank_name = models.CharField(
        max_length=150,
        help_text="Bank name (e.g. State Bank of India, HDFC Bank)"
    )
    account_number = models.CharField(
        max_length=50,
        help_text="Bank account number"
    )
    ifsc_code = models.CharField(
        max_length=30,
        help_text="Bank IFSC routing code"
    )
    branch_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Branch name and city"
    )
    account_purpose = models.CharField(
        max_length=20,
        choices=ACCOUNT_PURPOSE_CHOICES,
        default="FEES",
        help_text="Operational purpose of this bank account"
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Whether this account is the default primary account for fee receipts and tax invoices"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "school_bank_account"
        ordering = ["-is_primary", "-id"]
        verbose_name = "School Bank Account"
        verbose_name_plural = "School Bank Accounts"

    def __str__(self):
        primary_badge = " [PRIMARY]" if self.is_primary else ""
        return f"{self.bank_name} ({self.account_number}) - {self.account_purpose}{primary_badge}"

    def save(self, *args, **kwargs):
        # If this account is marked as primary, unmark any other accounts for the same school profile
        if self.is_primary and self.school_profile_id:
            SchoolBankAccount.objects.filter(
                school_profile_id=self.school_profile_id,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)

            # Keep legacy single bank fields on SchoolProfile in sync for backwards compatibility
            profile = self.school_profile
            profile.bank_account_name = self.account_holder_name
            profile.bank_account_no = self.account_number
            profile.bank_ifsc = self.ifsc_code
            branch_part = f", {self.branch_name}" if self.branch_name else ""
            profile.bank_name = f"{self.bank_name}{branch_part}"
            profile.save(update_fields=["bank_account_name", "bank_account_no", "bank_ifsc", "bank_name", "updated_at"])

        # If this is the only account for this profile, ensure it defaults to primary
        elif not self.is_primary and self.school_profile_id:
            has_other_primary = SchoolBankAccount.objects.filter(
                school_profile_id=self.school_profile_id,
                is_primary=True
            ).exclude(pk=self.pk).exists()
            if not has_other_primary:
                self.is_primary = True

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        was_primary = self.is_primary
        profile_id = self.school_profile_id
        super().delete(*args, **kwargs)
        if profile_id:
            remaining = SchoolBankAccount.objects.filter(school_profile_id=profile_id)
            if remaining.exists():
                if was_primary:
                    next_primary = remaining.first()
                    next_primary.is_primary = True
                    next_primary.save()
            else:
                # All bank accounts deleted: clear SchoolProfile legacy fields so it never resurrects!
                SchoolProfile.objects.filter(id=profile_id).update(
                    bank_account_name="",
                    bank_account_no="",
                    bank_ifsc="",
                    bank_name="",
                )
