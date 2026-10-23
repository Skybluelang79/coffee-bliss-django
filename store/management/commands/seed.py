"""Seed the database with demo data for Coffee Bliss.

Usage:
    python manage.py seed
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Address, LoyaltyTransaction, User
from inventory.models import Ingredient, RecipeItem, StockMovement, Supplier
from orders.models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    Reservation,
    Subscription,
    Table,
)
from store.models import (
    BaristaNote,
    BlogPost,
    BrewGuide,
    BrewStep,
    Category,
    Coupon,
    NewsletterSubscriber,
    Product,
    Review,
    StoreLocation,
    SubscriptionPlan,
    Tag,
)


DESCRIPTION = (
    "Handcrafted with our signature house blend, roasted in small batches for a "
    "smooth, balanced cup that keeps you coming back."
)


class Command(BaseCommand):
    help = "Populate the database with demo coffee shop data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing demo orders/products first.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("Flushing existing catalog & orders…")
            StockMovement.objects.all().delete()
            RecipeItem.objects.all().delete()
            Ingredient.objects.all().delete()
            Supplier.objects.all().delete()
            OrderItem.objects.all().delete()
            Order.objects.all().delete()
            Subscription.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            SubscriptionPlan.objects.all().delete()
            Coupon.objects.all().delete()

        admin = self._users()
        locations = self._locations()
        categories = self._categories()
        products = self._products(categories)
        self._tags(products)
        self._plans()
        self._coupons()
        self._tables()
        self._blog(admin)
        self._subscribers()
        self._reviews(products)
        self._brew_guides(products)
        self._inventory(products)
        self._orders(products, locations)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(products)} products, {len(categories)} categories. "
                f"Admin login: admin@coffeebliss.test / admin12345"
            )
        )

    def _users(self):
        admin, created = User.objects.get_or_create(
            email="admin@coffeebliss.test",
            defaults={
                "first_name": "Ada",
                "last_name": "Bliss",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "loyalty_points": 0,
            },
        )
        if created:
            admin.set_password("admin12345")
            admin.save()

        staff, created = User.objects.get_or_create(
            email="staff@coffeebliss.test",
            defaults={
                "first_name": "Sam",
                "last_name": "Barista",
                "role": User.Role.STAFF,
                "is_staff": True,
            },
        )
        if created:
            staff.set_password("staff12345")
            staff.save()

        for i in range(1, 9):
            user, created = User.objects.get_or_create(
                email=f"customer{i}@example.com",
                defaults={
                    "first_name": random.choice(["Mia", "Leo", "Zoe", "Kai", "Ava", "Noah", "Ivy", "Eli"]),
                    "last_name": random.choice(["Bean", "Roast", "Crema", "Mocha", "Latte"]),
                    "phone": f"+1 555 0{i:03d}",
                    "role": User.Role.CUSTOMER,
                    "loyalty_points": random.randint(50, 800),
                    "newsletter_opt_in": True,
                },
            )
            if created:
                user.set_password("demo12345")
                user.save()
                Address.objects.create(
                    user=user,
                    label="home",
                    recipient=user.get_full_name(),
                    line1=f"{random.randint(1, 300)} Roastery Lane",
                    city=random.choice(["Bean Town", "Roastville", "Crema City"]),
                    state="CA",
                    postal_code=f"9{random.randint(1000, 9999)}",
                    is_default=True,
                )
                LoyaltyTransaction.objects.create(
                    user=user, points=100, reason="signup", note="Welcome bonus"
                )
        return admin

    def _locations(self):
        data = [
            ("Downtown Roastery", "12 Roastery Lane", "Bean Town", "+1 555 010 2016", "Mon–Sun 7am–8pm"),
            ("Riverside Café", "88 Riverside Walk", "Crema City", "+1 555 010 2017", "Mon–Sun 8am–6pm"),
            ("Airport Kiosk", "Terminal B, Gate 12", "Bean Town", "+1 555 010 2018", "Daily 5am–10pm"),
        ]
        locations = []
        for name, address, city, phone, hours in data:
            location, _ = StoreLocation.objects.get_or_create(
                name=name,
                defaults={
                    "address": address,
                    "city": city,
                    "phone": phone,
                    "opening_hours": hours,
                },
            )
            locations.append(location)
        return locations

    def _categories(self):
        data = [
            ("Espresso & Coffee", "☕", "Classic espresso, lattes, cappuccinos and more."),
            ("Cold Brew", "🧊", "Slow-steeped, smooth and refreshing."),
            ("Tea & Chai", "🍵", "Premium loose-leaf teas and spiced chai."),
            ("Beans & Grounds", "🫘", "Freshly roasted beans for home brewing."),
            ("Bakery & Food", "🥐", "Pastries, sandwiches and sweet treats."),
            ("Merchandise", "🎁", "Mugs, tumblers and Coffee Bliss gear."),
        ]
        categories = {}
        for i, (name, icon, desc) in enumerate(data):
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={"icon": icon, "description": desc, "sort_order": i},
            )
            categories[name] = category
        return categories

    def _products(self, categories):
        catalog = [
            # (name, category, kind, roast, price, compare, featured, new, desc, origin)
            ("Signature House Blend", "Beans & Grounds", "beans", "medium", "16500.00", "19000.00", True, False, "Our flagship blend — chocolatey, nutty and endlessly drinkable.", "Colombia"),
            ("Ethiopia Yirgacheffe", "Beans & Grounds", "beans", "light", "21000.00", None, True, True, "Bright and floral with notes of jasmine and stone fruit.", "Ethiopia"),
            ("Sumatra Dark Roast", "Beans & Grounds", "beans", "dark", "18000.00", None, False, False, "Bold, earthy and full-bodied with a syrupy finish.", "Indonesia"),
            ("Classic Espresso", "Espresso & Coffee", "drink", "espresso", "3250.00", None, True, False, "A perfect double shot pulled from our house blend.", None),
            ("Caramel Latte", "Espresso & Coffee", "drink", "espresso", "4750.00", "5250.00", True, False, "Silky steamed milk, espresso and house caramel.", None),
            ("Vanilla Cappuccino", "Espresso & Coffee", "drink", "espresso", "4500.00", None, False, False, "Espresso topped with velvety microfoam and vanilla.", None),
            ("Flat White", "Espresso & Coffee", "drink", "espresso", "4600.00", None, True, False, "Ristretto shots with silky steamed milk.", None),
            ("Mocha Bliss", "Espresso & Coffee", "drink", "espresso", "5000.00", None, False, True, "Espresso, chocolate and cream — pure indulgence.", None),
            ("Vanilla Cold Brew", "Cold Brew", "drink", "espresso", "4950.00", None, True, False, "18-hour steeped cold brew with a touch of vanilla.", None),
            ("Salted Caramel Cold Brew", "Cold Brew", "drink", "espresso", "5250.00", "5750.00", False, False, "Cold brew swirled with salted caramel and cream.", None),
            ("Nitro Cold Brew", "Cold Brew", "drink", "espresso", "5500.00", None, True, True, "Nitrogen-infused for a cascading, creamy pour.", None),
            ("Spiced Chai Latte", "Tea & Chai", "drink", "na", "4400.00", None, False, False, "Aromatic masala chai with steamed milk.", None),
            ("Matcha Latte", "Tea & Chai", "drink", "na", "4900.00", None, False, True, "Ceremonial-grade matcha whisked with milk.", None),
            ("Butter Croissant", "Bakery & Food", "food", "na", "3500.00", None, False, False, "Flaky, buttery and baked fresh daily.", None),
            ("Almond Biscotti", "Bakery & Food", "food", "na", "2750.00", None, False, False, "Crunchy twice-baked biscotti — perfect with coffee.", None),
            ("Avocado Toast", "Bakery & Food", "food", "na", "7500.00", None, False, False, "Sourdough, smashed avocado, chili flakes and lime.", None),
            ("Coffee Bliss Ceramic Mug", "Merchandise", "merch", "na", "14000.00", None, False, False, "A 12oz hand-glazed ceramic mug in Cream.", None),
            ("Insulated Travel Tumbler", "Merchandise", "merch", "na", "24000.00", "28000.00", True, False, "Keeps drinks hot for 6 hours. Because you deserve it.", None),
        ]
        products = []
        for (name, cat, kind, roast, price, compare, featured, new, desc, origin) in catalog:
            product, _ = Product.objects.get_or_create(
                name=name,
                defaults={
                    "category": categories[cat],
                    "kind": kind,
                    "roast": roast,
                    "price": Decimal(price),
                    "compare_at_price": Decimal(compare) if compare else None,
                    "short_description": desc,
                    "description": f"{desc} {DESCRIPTION}",
                    "origin": origin or "",
                    "is_featured": featured,
                    "is_new": new,
                    "stock": random.choice([6, 12, 40, 120, 300]),
                    "calories": random.choice([None, 5, 120, 250]),
                    "caffeine_mg": random.choice([None, 63, 95, 150, 200]),
                    "prep_time_minutes": random.choice([3, 5, 7]),
                },
            )
            products.append(product)
        return products

    def _tags(self, products):
        names = ["Organic", "Fair Trade", "Best Seller", "Decaf Available", "Limited", "Vegan"]
        tags = []
        for name in names:
            tag, _ = Tag.objects.get_or_create(name=name)
            tags.append(tag)
        for product in products:
            product.tags.set(random.sample(tags, k=random.randint(0, 2)))

    def _plans(self):
        data = [
            ("Bean Curious", "A gentle intro to great coffee", "9000.00", "monthly", 1, False,
             "1 bag (250g) monthly\nFree delivery\nRoaster's choice\nPause anytime"),
            ("True Brew", "Our most popular subscription", "24000.00", "biweekly", 2, True,
             "2 bags (500g) every 2 weeks\nFree priority delivery\nChoose your roast\n10% off extras\nMembers-only beans"),
            ("Daily Ritual", "For the serious coffee lover", "39000.00", "weekly", 2, False,
             "2 bags (500g) weekly\nFree priority delivery\nPersonal roast profile\n20% off extras\nExclusive events"),
        ]
        for name, tagline, price, interval, bags, popular, perks in data:
            SubscriptionPlan.objects.get_or_create(
                name=name,
                defaults={
                    "tagline": tagline,
                    "description": tagline,
                    "price": Decimal(price),
                    "interval": interval,
                    "bags_per_delivery": bags,
                    "is_popular": popular,
                    "perks": perks,
                },
            )

    def _coupons(self):
        now = timezone.now()
        coupons = [
            ("WELCOME10", "10% off your first order", "percent", "10", "0"),
            ("BLISS5", "₦5,000 off orders over ₦25,000", "fixed", "5000", "25000"),
            ("BEANS20", "20% off beans", "percent", "20", "0"),
        ]
        for code, desc, dtype, value, minimum in coupons:
            Coupon.objects.get_or_create(
                code=code,
                defaults={
                    "description": desc,
                    "discount_type": dtype,
                    "value": Decimal(value),
                    "minimum_spend": Decimal(minimum),
                    "valid_until": now + timedelta(days=90),
                    "max_uses": 0,
                },
            )

    def _tables(self):
        for i in range(1, 9):
            Table.objects.get_or_create(name=f"T{i}", defaults={"seats": random.choice([2, 2, 4, 4, 6])})

    def _blog(self, admin):
        posts = [
            ("The art of the perfect pour-over", "Pour-over brewing rewards patience. Here's our barista-approved method for a clean, aromatic cup.", 5),
            ("What does 'single origin' really mean?", "Single origin coffee comes from one farm or region — and it tells a story. We break it down.", 4),
            ("Meet the farmers behind our house blend", "Great coffee starts at the source. A look at the direct-trade relationships we treasure.", 6),
        ]
        for title, excerpt, minutes in posts:
            BlogPost.objects.get_or_create(
                title=title,
                defaults={
                    "author": admin,
                    "excerpt": excerpt,
                    "body": f"{excerpt}\n\n" + "Coffee is a journey, and every step matters. " * 8,
                    "read_minutes": minutes,
                },
            )

    def _subscribers(self):
        for i in range(1, 6):
            NewsletterSubscriber.objects.get_or_create(
                email=f"subscriber{i}@example.com", defaults={"source": "seed"}
            )

    def _reviews(self, products):
        customers = User.objects.filter(role=User.Role.CUSTOMER)
        bodies = [
            "Absolutely delicious — my new daily ritual. The aroma alone is worth it.",
            "Smooth and full of flavour. Shipping was fast and the packaging is lovely.",
            "Best coffee I've had in ages. Reordering as we speak!",
            "Really enjoyed it, though I'd love a slightly bolder option too.",
            "Consistently great quality. The loyalty beans are a nice touch.",
        ]
        for product in products:
            for user in random.sample(list(customers), k=random.randint(0, 3)):
                Review.objects.get_or_create(
                    product=product,
                    user=user,
                    defaults={
                        "rating": random.randint(3, 5),
                        "title": random.choice(["Loved it", "So good", "A new favourite", ""]),
                        "body": random.choice(bodies),
                        "is_verified_purchase": random.choice([True, False]),
                    },
                )

    def _brew_guides(self, products):
        by_name = {p.name: p for p in products}
        guides = [
            {
                "product": "Signature House Blend",
                "title": "The everyday pour-over",
                "method": "pour_over",
                "description": "A forgiving, repeatable recipe that shows off the house blend's chocolate and nut notes.",
                "difficulty": "easy",
                "total_time_minutes": 5,
                "ratio": "1:15",
                "grind": "Medium-fine",
                "water_temp_c": 94,
                "yield_text": "1 cup (300 ml)",
                "steps": [
                    ("Rinse the filter", "Place a paper filter in your dripper and rinse it with hot water to warm the vessel and remove any papery taste.", 20, "Tip the rinse water away before you start."),
                    ("Add the coffee", "Weigh 20 g of medium-fine ground coffee into the filter and level the bed.", 15, ""),
                    ("Bloom", "Pour 60 ml of water and wait for the coffee to bloom and release its gases.", 35, "Fresh beans will bubble enthusiastically here."),
                    ("First pour", "Pour in slow circles up to 180 ml, keeping the bed even.", 30, ""),
                    ("Finish", "Top up to 300 ml, then let it drain fully.", 60, "Pull the dripper off before the bed dries out."),
                ],
            },
            {
                "product": "Classic Espresso",
                "title": "Dial in the perfect double shot",
                "method": "espresso",
                "description": "A 1:2 classic espresso recipe you can fine-tune to taste.",
                "difficulty": "medium",
                "total_time_minutes": 3,
                "ratio": "1:2",
                "grind": "Fine",
                "water_temp_c": 93,
                "yield_text": "36 g out",
                "steps": [
                    ("Dose", "Grind 18 g of coffee into your dry basket.", 15, "A dry basket keeps the dose consistent."),
                    ("Distribute & tamp", "Level the grounds, then tamp straight down with firm, even pressure.", 15, "Consistency beats brute force on the tamp."),
                    ("Extract", "Start the shot immediately and watch the flow.", 28, "Aim for 36 g out in 25–30 seconds."),
                    ("Taste & adjust", "Too fast and sour? Grind finer. Slow and bitter? Grind coarser.", 20, "Change one variable at a time."),
                ],
            },
            {
                "product": "Vanilla Cold Brew",
                "title": "Overnight cold brew concentrate",
                "method": "cold_brew",
                "description": "Smooth, low-acid cold brew you can keep in the fridge all week.",
                "difficulty": "easy",
                "total_time_minutes": 720,
                "ratio": "1:5",
                "grind": "Coarse",
                "yield_text": "600 ml concentrate",
                "steps": [
                    ("Combine", "Add 120 g of coarsely ground coffee to 600 ml of cold filtered water.", 60, "Coarse grounds keep the brew clean."),
                    ("Steep", "Cover and leave in the fridge to steep.", 64800, "12–18 hours is the sweet spot."),
                    ("Strain", "Strain through a fine sieve lined with a paper filter.", 120, "Avoid pressing the grounds — it adds bitterness."),
                    ("Serve", "Dilute 1:1 with water or milk over ice.", 30, "Keeps for up to a week refrigerated."),
                ],
            },
        ]
        guide_count = 0
        for data in guides:
            product = by_name.get(data["product"])
            if not product:
                continue
            guide, _ = BrewGuide.objects.get_or_create(
                product=product,
                title=data["title"],
                defaults={
                    "method": data["method"],
                    "description": data["description"],
                    "difficulty": data["difficulty"],
                    "total_time_minutes": data["total_time_minutes"],
                    "ratio": data["ratio"],
                    "grind": data["grind"],
                    "water_temp_c": data.get("water_temp_c"),
                    "yield_text": data["yield_text"],
                },
            )
            if guide.steps.count() == 0:
                for i, (title, instruction, duration, tip) in enumerate(data["steps"]):
                    BrewStep.objects.create(
                        guide=guide,
                        order=i,
                        title=title,
                        instruction=instruction,
                        duration_seconds=duration,
                        tip=tip,
                    )
            guide_count += 1

        notes = [
            ("Signature House Blend", "Marta, Head Roaster", "Let the beans rest a few days after roast — the chocolate notes really open up."),
            ("Classic Espresso", "Sam, Lead Barista", "If the shot runs sour, don't touch the recipe yet — try a slightly finer grind first."),
            ("Nitro Cold Brew", "Nadia, Café Manager", "Serve it cold, cold, cold. Room-temperature glassware kills the cascade."),
        ]
        note_count = 0
        for product_name, author, body in notes:
            product = by_name.get(product_name)
            if not product:
                continue
            BaristaNote.objects.get_or_create(
                product=product, body=body, defaults={"author": author}
            )
            note_count += 1

        self.stdout.write(
            f"Seeded {guide_count} brew guides and {note_count} barista notes."
        )

    def _inventory(self, products):
        suppliers_data = [
            ("Roaster's Guild", "Marta Vela", "orders@roastersguild.example", 2),
            ("Greenline Dairy", "Tom Fields", "hello@greenlinedairy.example", 1),
            ("SweetLeaf Syrups", "Nadia Kun", "sales@sweetleaf.example", 4),
            ("PackRight Supplies", "Ben Ortiz", "support@packright.example", 5),
        ]
        suppliers = []
        for name, contact, email, lead in suppliers_data:
            supplier, _ = Supplier.objects.get_or_create(
                name=name,
                defaults={
                    "contact_name": contact,
                    "email": email,
                    "phone": f"+1 555 020 {random.randint(1000, 9999)}",
                    "lead_time_days": lead,
                },
            )
            suppliers.append(supplier)

        ingredients_data = [
            # (name, sku, unit, stock, reorder, par, cost, supplier_idx)
            ("House Blend Beans", "BEAN-HB", "g", 42000, 8000, 40000, "18.0000", 0),
            ("Espresso Roast Beans", "BEAN-ES", "g", 26000, 6000, 30000, "19.5000", 0),
            ("Decaf Beans", "BEAN-DC", "g", 4200, 3000, 12000, "21.0000", 0),
            ("Whole Milk", "MILK-WH", "ml", 31000, 10000, 40000, "1.1000", 1),
            ("Oat Milk", "MILK-OT", "ml", 8600, 8000, 30000, "2.4000", 1),
            ("Vanilla Syrup", "SYR-VN", "ml", 5400, 2000, 8000, "5.2000", 2),
            ("Caramel Syrup", "SYR-CR", "ml", 1800, 2000, 8000, "5.5000", 2),
            ("Salted Caramel Syrup", "SYR-SC", "ml", 900, 1500, 6000, "6.0000", 2),
            ("Matcha Powder", "PWD-MT", "g", 1200, 500, 2000, "95.0000", 2),
            ("Chai Concentrate", "CNC-CH", "ml", 3600, 1500, 6000, "4.0000", 2),
            ("Cocoa Powder", "PWD-CC", "g", 2400, 800, 3000, "12.0000", 2),
            ("Butter", "DAI-BT", "g", 5200, 3000, 10000, "7.5000", 1),
            ("Croissant Dough", "BAK-CR", "ea", 48, 24, 120, "650.0000", 3),
            ("Sourdough Bread", "BAK-SD", "ea", 22, 20, 60, "1200.0000", 3),
            ("Avocado", "FRH-AV", "ea", 36, 24, 80, "900.0000", 3),
            ("12oz Paper Cups", "PKG-C12", "ea", 620, 500, 2000, "80.0000", 3),
            ("16oz Paper Cups", "PKG-C16", "ea", 480, 500, 2000, "95.0000", 3),
            ("Cup Lids", "PKG-LID", "ea", 1450, 600, 2500, "30.0000", 3),
        ]
        ingredients = {}
        for (name, sku, unit, stock, reorder, par, cost, s_idx) in ingredients_data:
            ingredient, _ = Ingredient.objects.get_or_create(
                name=name,
                defaults={
                    "sku": sku,
                    "unit": unit,
                    "stock": Decimal(stock),
                    "reorder_level": Decimal(reorder),
                    "par_level": Decimal(par),
                    "cost_per_unit": Decimal(cost),
                    "supplier": suppliers[s_idx],
                },
            )
            if ingredient.movements.count() == 0:
                StockMovement.objects.create(
                    ingredient=ingredient,
                    kind=StockMovement.Kind.PURCHASE,
                    quantity=ingredient.stock,
                    unit=ingredient.unit,
                    unit_cost=ingredient.cost_per_unit,
                    reason="Opening stock",
                )
            ingredients[name] = ingredient

        # Recipes: map menu drinks to the ingredients they consume.
        recipes = {
            "Classic Espresso": [("Espresso Roast Beans", 18), ("12oz Paper Cups", 1), ("Cup Lids", 1)],
            "Caramel Latte": [("Espresso Roast Beans", 18), ("Whole Milk", 220), ("Caramel Syrup", 20), ("16oz Paper Cups", 1), ("Cup Lids", 1)],
            "Vanilla Cappuccino": [("Espresso Roast Beans", 18), ("Whole Milk", 200), ("Vanilla Syrup", 15), ("16oz Paper Cups", 1), ("Cup Lids", 1)],
            "Flat White": [("Espresso Roast Beans", 20), ("Whole Milk", 160), ("12oz Paper Cups", 1), ("Cup Lids", 1)],
            "Mocha Bliss": [("Espresso Roast Beans", 18), ("Whole Milk", 200), ("Cocoa Powder", 20), ("16oz Paper Cups", 1), ("Cup Lids", 1)],
            "Vanilla Cold Brew": [("House Blend Beans", 40), ("Vanilla Syrup", 20), ("16oz Paper Cups", 1), ("Cup Lids", 1)],
            "Salted Caramel Cold Brew": [("House Blend Beans", 40), ("Salted Caramel Syrup", 25), ("16oz Paper Cups", 1), ("Cup Lids", 1)],
            "Nitro Cold Brew": [("House Blend Beans", 45), ("16oz Paper Cups", 1), ("Cup Lids", 1)],
            "Spiced Chai Latte": [("Chai Concentrate", 60), ("Whole Milk", 180), ("16oz Paper Cups", 1), ("Cup Lids", 1)],
            "Matcha Latte": [("Matcha Powder", 3), ("Whole Milk", 200), ("16oz Paper Cups", 1), ("Cup Lids", 1)],
            "Butter Croissant": [("Croissant Dough", 1), ("Butter", 30)],
            "Avocado Toast": [("Sourdough Bread", 1), ("Avocado", 1)],
        }
        by_name = {p.name: p for p in products}
        for product_name, lines in recipes.items():
            product = by_name.get(product_name)
            if not product:
                continue
            for ing_name, qty in lines:
                RecipeItem.objects.update_or_create(
                    product=product,
                    ingredient=ingredients[ing_name],
                    defaults={"quantity": Decimal(qty)},
                )

        # Merchandise and bean bags are not stock-tracked as drinks.
        Product.objects.filter(kind__in=["merch", "beans"]).update(track_stock=False)

        self.stdout.write(
            f"Seeded {len(suppliers)} suppliers, {len(ingredients)} ingredients, "
            f"{sum(1 for n in recipes if n in by_name)} recipes."
        )
        return ingredients

    def _orders(self, products, locations):
        customers = list(User.objects.filter(role=User.Role.CUSTOMER))
        for i in range(20):
            user = random.choice(customers)
            fulfillment = random.choice(["pickup", "delivery", "dine_in"])
            # Keep demo orders recent (within the last ~6 hours) so the live
            # kitchen board and "today" reports look realistic.
            minutes_ago = random.randint(1, 360)
            if minutes_ago < 60:
                status = random.choice(["pending", "confirmed", "preparing", "ready"])
            elif minutes_ago < 180:
                status = random.choice(["confirmed", "preparing", "ready", "completed", "completed"])
            else:
                status = random.choice(
                    ["ready", "out_for_delivery", "completed", "completed", "completed"]
                )
            order = Order.objects.create(
                user=user,
                status=status,
                fulfillment=fulfillment,
                location=random.choice(locations),
                customer_name=user.get_full_name(),
                customer_phone=user.phone,
                delivery_address="12 Roastery Lane, Bean Town" if fulfillment == "delivery" else "",
            )
            for product in random.sample(products, k=random.randint(1, 4)):
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    name=product.name,
                    unit_price=product.price,
                    quantity=random.randint(1, 3),
                )
            order = order.recalculate()
            order.payment_status = Order.PaymentStatus.PAID
            placed = timezone.now() - timedelta(minutes=minutes_ago)
            order.placed_at = placed
            order.save()
            Order.objects.filter(pk=order.pk).update(created_at=placed)
            Payment.objects.create(
                order=order,
                method=random.choice(["card", "wallet", "cash"]),
                amount=order.total,
                state=Payment.State.SUCCEEDED,
                is_successful=True,
                reference=f"SEED-{order.number}",
            )
            OrderStatusHistory.objects.create(order=order, status=order.status, note="Seeded")
