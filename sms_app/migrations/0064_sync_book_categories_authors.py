from django.db import migrations

def sync_categories_and_authors(apps, schema_editor):
    Book = apps.get_model('sms_app', 'Book')
    BookCategory = apps.get_model('sms_app', 'BookCategory')
    Author = apps.get_model('sms_app', 'Author')

    for b in Book.objects.all():
        school = b.school
        cat_name = (b.category or '').strip()
        if cat_name:
            cat_obj = BookCategory.objects.filter(school=school, name__iexact=cat_name).first()
            if not cat_obj:
                cat_obj = BookCategory.objects.create(
                    school=school,
                    name=cat_name.title(),
                    is_active=True
                )
            elif not cat_obj.is_active:
                cat_obj.is_active = True
                cat_obj.save(update_fields=['is_active'])
            if not getattr(b, 'category_ref_id', None):
                b.category_ref = cat_obj
                b.save(update_fields=['category_ref'])

        auth_name = (b.author or '').strip()
        if auth_name:
            auth_obj = Author.objects.filter(school=school, name__iexact=auth_name).first()
            if not auth_obj:
                auth_obj = Author.objects.create(
                    school=school,
                    name=auth_name.title(),
                    is_active=True
                )
            elif not auth_obj.is_active:
                auth_obj.is_active = True
                auth_obj.save(update_fields=['is_active'])
            if not getattr(b, 'author_ref_id', None):
                b.author_ref = auth_obj
                b.save(update_fields=['author_ref'])

class Migration(migrations.Migration):

    dependencies = [
        ('sms_app', '0063_bookcopy_unique_school_book_copy_barcode'),
    ]

    operations = [
        migrations.RunPython(sync_categories_and_authors, reverse_code=migrations.RunPython.noop),
    ]
