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
    board_affiliation = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Affiliation board (e.g. CBSE, ICSE, GSEB, State Board, IB)"
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
        return profile

