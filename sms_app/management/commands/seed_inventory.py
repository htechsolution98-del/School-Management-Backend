from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from sms_app.models import School
from sms_app.inventory_models import (
    InventoryCategory,
    InventorySubCategory,
    InventoryUnit,
    InventoryWarehouse,
    InventorySupplier,
    InventoryItem,
    InventoryItemVariant,
    InventoryBundle,
    InventoryBundleItem,
)
from sms_app.inventory_services import process_opening_stock


class Command(BaseCommand):
    help = "Seed default standard inventory categories, units, warehouses, and items for schools."

    def handle(self, *args, **kwargs):
        schools = School.objects.all()
        if not schools.exists():
            self.stdout.write(self.style.WARNING("No schools found to seed inventory."))
            return

        for school in schools:
            self.stdout.write(f"Seeding inventory for School: {school.name}...")

            # 1. Standard Units
            units_data = [
                ("Pieces", "PCS"),
                ("Pair", "PR"),
                ("Box", "BOX"),
                ("Kilogram", "KG"),
                ("Meter", "M"),
                ("Ream", "RM"),
                ("Set", "SET"),
                ("Packet", "PKT"),
            ]
            for name, sym in units_data:
                InventoryUnit.objects.get_or_create(school=school, name=name, defaults={"symbol": sym})

            # 2. Warehouses
            wh_data = [
                ("WH-CENTRAL", "Central Main Store", "Ground Floor - Admin Block"),
                ("WH-UNIFORM", "Uniform & Student Store", "Building B - Room 102"),
                ("WH-SPORTS", "Sports Equipment Room", "Ground Pavilion"),
                ("WH-SCIENCE", "Science Laboratory Store", "Science Block - 2nd Floor"),
                ("WH-IT", "IT & Computer Warehouse", "Computer Lab A"),
                ("WH-STATIONERY", "Stationery & Exam Store", "Admin Building - 1st Floor"),
            ]
            warehouses = {}
            for code, name, loc in wh_data:
                wh, _ = InventoryWarehouse.objects.get_or_create(
                    school=school,
                    warehouse_code=code,
                    defaults={"warehouse_name": name, "location": loc, "is_active": True}
                )
                warehouses[code] = wh

            # 3. Categories & Subcategories
            cat_data = [
                ("Student Items", "STUDENT", [
                    ("School Uniforms", "UNIFORM"),
                    ("Footwear & Shoes", "SHOES"),
                    ("Accessories (Tie, Belt, Badges)", "ACC"),
                    ("Student ID Cards", "IDCARD"),
                    ("School Bags & Kit", "KIT"),
                ]),
                ("Stationery & Consumables", "STATIONERY", [
                    ("Writing Materials", "PENS"),
                    ("Paper & Notebooks", "PAPER"),
                    ("Chalk & Duster", "CHALK"),
                    ("Office Files & Folders", "FILES"),
                ]),
                ("Assets & Electronics", "ASSETS", [
                    ("Laptops & Desktops", "COMP"),
                    ("Projectors & AV", "AV"),
                    ("Classroom Furniture", "FURN"),
                ]),
                ("Sports Equipment", "SPORTS", [
                    ("Cricket Kit", "CRIC"),
                    ("Football & Basketball", "BALL"),
                    ("Athletics & Indoor", "ATH"),
                ]),
                ("Laboratory Supplies", "LAB", [
                    ("Physics Apparatus", "PHY"),
                    ("Chemistry Chemicals & Glassware", "CHEM"),
                    ("Biology Models", "BIO"),
                ]),
                ("Cleaning & Maintenance", "CLEAN", [
                    ("Cleaning Detergents & Sanitizers", "DET"),
                    ("Maintenance Hardware", "MAINT"),
                ]),
            ]

            categories = {}
            subcategories = {}
            for c_name, c_code, subs in cat_data:
                cat, _ = InventoryCategory.objects.get_or_create(
                    school=school,
                    name=c_name,
                    defaults={"code": c_code, "is_active": True}
                )
                categories[c_code] = cat
                for s_name, s_code in subs:
                    sub, _ = InventorySubCategory.objects.get_or_create(
                        school=school,
                        category=cat,
                        name=s_name,
                        defaults={"code": s_code, "is_active": True}
                    )
                    subcategories[s_code] = sub

            # 4. Suppliers
            supp_data = [
                ("Apex School Uniforms & Apparels", "Rajesh Sharma", "9876543210", "uniforms@apextextiles.com", "Surat, Gujarat", "24AAAAA0000A1Z5"),
                ("National Book & Stationery Depot", "Vikas Gupta", "9822334455", "orders@nationalstationery.com", "Ahmedabad, Gujarat", "24BBBBB1111B2Z6"),
                ("Zenith IT Solutions & Hardware", "Priya Mehta", "9898989898", "sales@zenithtech.in", "Mumbai, Maharashtra", "27CCCCC2222C3Z7"),
                ("Champion Sports Gear Ltd", "Amit Singh", "9712345678", "contact@championsports.in", "New Delhi", "07DDDDD3333D4Z8"),
            ]
            for sname, cperson, phone, email, addr, gst in supp_data:
                InventorySupplier.objects.get_or_create(
                    school=school,
                    name=sname,
                    defaults={
                        "contact_person": cperson,
                        "phone": phone,
                        "email": email,
                        "address": addr,
                        "gst_number": gst,
                        "is_active": True,
                    }
                )

            # 5. Items with Variants & Opening Stock
            items_config = [
                {
                    "code": "UNI-SHIRT-W",
                    "name": "School Uniform Shirt (White)",
                    "cat": "STUDENT",
                    "sub": "UNIFORM",
                    "type": "STUDENT_ITEM",
                    "unit": "PCS",
                    "track_size": True,
                    "min_stock": 20,
                    "purchase_price": Decimal("250.00"),
                    "issue_price": Decimal("350.00"),
                    "wh": "WH-UNIFORM",
                    "variants": [
                        ("UNI-SHIRT-W-28", "28", "White", "UNISEX", 25),
                        ("UNI-SHIRT-W-30", "30", "White", "UNISEX", 40),
                        ("UNI-SHIRT-W-32", "32", "White", "UNISEX", 50),
                        ("UNI-SHIRT-W-34", "34", "White", "UNISEX", 45),
                        ("UNI-SHIRT-W-36", "36", "White", "UNISEX", 30),
                    ],
                },
                {
                    "code": "UNI-PANT-NV",
                    "name": "School Uniform Trousers (Navy Blue)",
                    "cat": "STUDENT",
                    "sub": "UNIFORM",
                    "type": "STUDENT_ITEM",
                    "unit": "PCS",
                    "track_size": True,
                    "min_stock": 20,
                    "purchase_price": Decimal("300.00"),
                    "issue_price": Decimal("450.00"),
                    "wh": "WH-UNIFORM",
                    "variants": [
                        ("UNI-PANT-28", "28", "Navy Blue", "UNISEX", 20),
                        ("UNI-PANT-30", "30", "Navy Blue", "UNISEX", 35),
                        ("UNI-PANT-32", "32", "Navy Blue", "UNISEX", 40),
                        ("UNI-PANT-34", "34", "Navy Blue", "UNISEX", 30),
                    ],
                },
                {
                    "code": "SHOE-BLACK",
                    "name": "Standard Black School Shoes",
                    "cat": "STUDENT",
                    "sub": "SHOES",
                    "type": "STUDENT_ITEM",
                    "unit": "PR",
                    "track_size": True,
                    "min_stock": 15,
                    "purchase_price": Decimal("400.00"),
                    "issue_price": Decimal("550.00"),
                    "wh": "WH-UNIFORM",
                    "variants": [
                        ("SHOE-BLK-06", "6", "Black", "UNISEX", 20),
                        ("SHOE-BLK-07", "7", "Black", "UNISEX", 25),
                        ("SHOE-BLK-08", "8", "Black", "UNISEX", 30),
                        ("SHOE-BLK-09", "9", "Black", "UNISEX", 20),
                    ],
                },
                {
                    "code": "ACC-TIE-01",
                    "name": "School Striped Tie",
                    "cat": "STUDENT",
                    "sub": "ACC",
                    "type": "STUDENT_ITEM",
                    "unit": "PCS",
                    "track_size": False,
                    "min_stock": 30,
                    "purchase_price": Decimal("50.00"),
                    "issue_price": Decimal("80.00"),
                    "wh": "WH-UNIFORM",
                    "opening_qty": 150,
                },
                {
                    "code": "ACC-BELT-01",
                    "name": "School Crest Belt",
                    "cat": "STUDENT",
                    "sub": "ACC",
                    "type": "STUDENT_ITEM",
                    "unit": "PCS",
                    "track_size": False,
                    "min_stock": 30,
                    "purchase_price": Decimal("60.00"),
                    "issue_price": Decimal("90.00"),
                    "wh": "WH-UNIFORM",
                    "opening_qty": 120,
                },
                {
                    "code": "ID-BLANK-CARD",
                    "name": "Smart PVC Student ID Card (Blank)",
                    "cat": "STUDENT",
                    "sub": "IDCARD",
                    "type": "STUDENT_ITEM",
                    "unit": "PCS",
                    "track_size": False,
                    "min_stock": 50,
                    "purchase_price": Decimal("25.00"),
                    "issue_price": Decimal("50.00"),
                    "wh": "WH-CENTRAL",
                    "opening_qty": 300,
                },
                {
                    "code": "STN-A4-REAMS",
                    "name": "JK Copier A4 Paper (75 GSM Ream)",
                    "cat": "STATIONERY",
                    "sub": "PAPER",
                    "type": "STATIONERY",
                    "unit": "RM",
                    "track_size": False,
                    "min_stock": 10,
                    "purchase_price": Decimal("220.00"),
                    "issue_price": Decimal("260.00"),
                    "wh": "WH-STATIONERY",
                    "opening_qty": 60,
                },
                {
                    "code": "SPT-CRIC-BAT",
                    "name": "English Willow Cricket Bat (Grade 1)",
                    "cat": "SPORTS",
                    "sub": "CRIC",
                    "type": "SPORTS",
                    "unit": "PCS",
                    "track_size": False,
                    "min_stock": 5,
                    "purchase_price": Decimal("1800.00"),
                    "issue_price": Decimal("2200.00"),
                    "wh": "WH-SPORTS",
                    "opening_qty": 12,
                },
            ]

            for cfg in items_config:
                item, created = InventoryItem.objects.get_or_create(
                    school=school,
                    item_code=cfg["code"],
                    defaults={
                        "item_name": cfg["name"],
                        "category": categories.get(cfg["cat"]),
                        "sub_category": subcategories.get(cfg["sub"]),
                        "item_type": cfg["type"],
                        "unit": cfg["unit"],
                        "track_size": cfg.get("track_size", False),
                        "minimum_stock": cfg.get("min_stock", 10),
                        "purchase_price": cfg["purchase_price"],
                        "issue_price": cfg["issue_price"],
                        "is_active": True,
                    }
                )

                wh = warehouses.get(cfg.get("wh", "WH-CENTRAL"))

                if "variants" in cfg:
                    for v_code, v_size, v_color, v_gender, v_qty in cfg["variants"]:
                        var, v_created = InventoryItemVariant.objects.get_or_create(
                            item=item,
                            variant_code=v_code,
                            defaults={
                                "size": v_size,
                                "color": v_color,
                                "gender": v_gender,
                                "purchase_price": cfg["purchase_price"],
                                "issue_price": cfg["issue_price"],
                                "minimum_stock": 5,
                                "is_active": True,
                            }
                        )
                        # Add opening stock if created
                        if v_created and v_qty > 0:
                            process_opening_stock(
                                school=school,
                                item=item,
                                warehouse=wh,
                                quantity=v_qty,
                                unit_cost=cfg["purchase_price"],
                                variant=var,
                                remarks=f"Initial Opening Stock for {cfg['name']} (Size {v_size})"
                            )
                elif "opening_qty" in cfg and created:
                    process_opening_stock(
                        school=school,
                        item=item,
                        warehouse=wh,
                        quantity=cfg["opening_qty"],
                        unit_cost=cfg["purchase_price"],
                        remarks=f"Initial Opening Stock for {cfg['name']}"
                    )

            # 6. Sample Student Uniform Kit / Bundle
            shirt = InventoryItem.objects.filter(school=school, item_code="UNI-SHIRT-W").first()
            pant = InventoryItem.objects.filter(school=school, item_code="UNI-PANT-NV").first()
            tie = InventoryItem.objects.filter(school=school, item_code="ACC-TIE-01").first()
            belt = InventoryItem.objects.filter(school=school, item_code="ACC-BELT-01").first()

            if shirt and pant and tie and belt:
                bundle, b_created = InventoryBundle.objects.get_or_create(
                    school=school,
                    bundle_code="KIT-UNIFORM-FULL",
                    defaults={
                        "bundle_name": "Complete School Uniform Kit (Shirt, Pant, Tie, Belt)",
                        "description": "Standard all-in-one uniform distribution package for students.",
                        "applicable_gender": "UNISEX",
                        "total_price": Decimal("950.00"),
                        "is_active": True,
                    }
                )
                if b_created:
                    InventoryBundleItem.objects.create(bundle=bundle, item=shirt, quantity=1)
                    InventoryBundleItem.objects.create(bundle=bundle, item=pant, quantity=1)
                    InventoryBundleItem.objects.create(bundle=bundle, item=tie, quantity=1)
                    InventoryBundleItem.objects.create(bundle=bundle, item=belt, quantity=1)

        self.stdout.write(self.style.SUCCESS("Successfully seeded comprehensive inventory dataset!"))
