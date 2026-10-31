from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sms_app", "0075_merge_20261031_1038"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE IF EXISTS school_profile 
            ALTER COLUMN board_affiliation DROP DEFAULT;

            ALTER TABLE IF EXISTS school_profile 
            ALTER COLUMN board_affiliation TYPE jsonb 
            USING (
                CASE 
                    WHEN board_affiliation IS NULL OR TRIM(board_affiliation::text) = '' THEN '[]'::jsonb
                    WHEN TRIM(board_affiliation::text) LIKE '[%' THEN board_affiliation::jsonb
                    ELSE jsonb_build_array(board_affiliation::text)
                END
            );

            ALTER TABLE IF EXISTS school_profile 
            ALTER COLUMN board_affiliation SET DEFAULT '[]'::jsonb;

            ALTER TABLE IF EXISTS sms_app_schoolprofile 
            ALTER COLUMN board_affiliation DROP DEFAULT;

            ALTER TABLE IF EXISTS sms_app_schoolprofile 
            ALTER COLUMN board_affiliation TYPE jsonb 
            USING (
                CASE 
                    WHEN board_affiliation IS NULL OR TRIM(board_affiliation::text) = '' THEN '[]'::jsonb
                    WHEN TRIM(board_affiliation::text) LIKE '[%' THEN board_affiliation::jsonb
                    ELSE jsonb_build_array(board_affiliation::text)
                END
            );

            ALTER TABLE IF EXISTS sms_app_schoolprofile 
            ALTER COLUMN board_affiliation SET DEFAULT '[]'::jsonb;
            """,
            reverse_sql="""
            ALTER TABLE IF EXISTS school_profile 
            ALTER COLUMN board_affiliation TYPE varchar(255) 
            USING board_affiliation#>>'{}';

            ALTER TABLE IF EXISTS sms_app_schoolprofile 
            ALTER COLUMN board_affiliation TYPE varchar(255) 
            USING board_affiliation#>>'{}';
            """,
        ),
        migrations.AlterField(
            model_name="schoolprofile",
            name="board_affiliation",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
