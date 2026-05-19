"""Dimension table generators for test data."""

import random
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pyarrow as pa
import pyarrow.parquet as pq

from .config import GeneratorConfig


@dataclass
class Category:
    id: int
    name: str


@dataclass
class Brand:
    id: int
    name: str
    cuisine_type: str
    avg_prep_time_mins: int
    momentum: str  # "growing", "stable", "declining"


@dataclass
class Item:
    id: int
    brand_id: int
    name: str
    price: float
    category_id: int


# Predefined dimension data
CATEGORIES = [
    Category(1, "Appetizers"),
    Category(2, "Main Course"),
    Category(3, "Sides"),
    Category(4, "Desserts"),
    Category(5, "Beverages"),
    Category(6, "Salads"),
    Category(7, "Soups"),
    Category(8, "Sandwiches"),
    Category(9, "Pizza"),
    Category(10, "Asian"),
]

BRANDS = [
    Brand(1, "Burger Republic", "American", 12, "stable"),
    Brand(2, "Wok This Way", "Chinese", 15, "growing"),
    Brand(3, "Pizza Planet", "Italian", 18, "stable"),
    Brand(4, "Taco Tornado", "Mexican", 10, "growing"),
    Brand(5, "Sushi Express", "Japanese", 20, "growing"),
    Brand(6, "Wing Commander", "American", 14, "stable"),
    Brand(7, "Curry House", "Indian", 22, "growing"),
    Brand(8, "Mediterranean Grill", "Mediterranean", 16, "stable"),
    Brand(9, "Pho Real", "Vietnamese", 18, "stable"),
    Brand(10, "BBQ Pitmaster", "American", 25, "declining"),
    Brand(11, "Salad Station", "Healthy", 8, "growing"),
    Brand(12, "Noodle Nirvana", "Asian Fusion", 14, "stable"),
    Brand(13, "Fried Chicken Co", "American", 15, "stable"),
    Brand(14, "Greek Gods", "Greek", 12, "stable"),
    Brand(15, "Thai Street", "Thai", 16, "growing"),
    Brand(16, "Breakfast Club", "Breakfast", 10, "stable"),
    Brand(17, "Smoothie Bowl", "Healthy", 6, "growing"),
    Brand(18, "Ramen House", "Japanese", 18, "stable"),
    Brand(19, "Soul Food Kitchen", "Southern", 20, "declining"),
    Brand(20, "Vegan Vibes", "Vegan", 14, "growing"),
]

# Items per brand (brand_id -> list of (name, price, category_id))
ITEMS_BY_BRAND = {
    1: [  # Burger Republic
        ("Classic Burger", 12.99, 2), ("Cheese Burger", 13.99, 2),
        ("Bacon Burger", 15.99, 2), ("Veggie Burger", 11.99, 2),
        ("Fries", 4.99, 3), ("Onion Rings", 5.99, 3),
        ("Milkshake", 6.99, 5), ("Soda", 2.99, 5),
    ],
    2: [  # Wok This Way
        ("Kung Pao Chicken", 14.99, 10), ("Beef Broccoli", 15.99, 10),
        ("Fried Rice", 10.99, 10), ("Lo Mein", 11.99, 10),
        ("Spring Rolls", 6.99, 1), ("Egg Drop Soup", 4.99, 7),
        ("Orange Chicken", 13.99, 10), ("General Tso", 14.99, 10),
    ],
    3: [  # Pizza Planet
        ("Margherita Pizza", 16.99, 9), ("Pepperoni Pizza", 18.99, 9),
        ("Supreme Pizza", 21.99, 9), ("Veggie Pizza", 17.99, 9),
        ("Garlic Bread", 5.99, 1), ("Caesar Salad", 8.99, 6),
        ("Tiramisu", 7.99, 4), ("Cannoli", 5.99, 4),
    ],
    4: [  # Taco Tornado
        ("Street Tacos", 11.99, 2), ("Burrito Bowl", 13.99, 2),
        ("Quesadilla", 10.99, 2), ("Nachos", 9.99, 1),
        ("Churros", 5.99, 4), ("Horchata", 3.99, 5),
        ("Guacamole", 4.99, 1), ("Elote", 4.99, 3),
    ],
    5: [  # Sushi Express
        ("California Roll", 12.99, 10), ("Salmon Sashimi", 16.99, 10),
        ("Spicy Tuna Roll", 14.99, 10), ("Dragon Roll", 18.99, 10),
        ("Miso Soup", 3.99, 7), ("Edamame", 5.99, 1),
        ("Tempura", 9.99, 1), ("Green Tea", 2.99, 5),
    ],
    6: [  # Wing Commander
        ("Buffalo Wings", 13.99, 2), ("BBQ Wings", 13.99, 2),
        ("Garlic Parmesan Wings", 14.99, 2), ("Boneless Wings", 12.99, 2),
        ("Celery & Carrots", 3.99, 3), ("Ranch Dip", 1.99, 3),
        ("Cheese Fries", 6.99, 3), ("Coleslaw", 3.99, 6),
    ],
    7: [  # Curry House
        ("Chicken Tikka Masala", 16.99, 2), ("Lamb Vindaloo", 18.99, 2),
        ("Palak Paneer", 14.99, 2), ("Biryani", 15.99, 2),
        ("Samosas", 6.99, 1), ("Naan Bread", 3.99, 3),
        ("Mango Lassi", 4.99, 5), ("Gulab Jamun", 5.99, 4),
    ],
    8: [  # Mediterranean Grill
        ("Chicken Shawarma", 14.99, 2), ("Lamb Gyro", 15.99, 2),
        ("Falafel Plate", 12.99, 2), ("Hummus Plate", 9.99, 1),
        ("Tabbouleh", 6.99, 6), ("Baklava", 5.99, 4),
        ("Pita Bread", 2.99, 3), ("Lemonade", 3.99, 5),
    ],
    9: [  # Pho Real
        ("Beef Pho", 14.99, 7), ("Chicken Pho", 13.99, 7),
        ("Bun Bo Hue", 15.99, 7), ("Banh Mi", 10.99, 8),
        ("Spring Rolls", 6.99, 1), ("Vietnamese Coffee", 4.99, 5),
        ("Vermicelli Bowl", 13.99, 2), ("Egg Rolls", 5.99, 1),
    ],
    10: [  # BBQ Pitmaster
        ("Brisket Plate", 19.99, 2), ("Pulled Pork", 15.99, 2),
        ("Ribs Half Rack", 22.99, 2), ("Smoked Chicken", 14.99, 2),
        ("Mac & Cheese", 5.99, 3), ("Baked Beans", 4.99, 3),
        ("Cornbread", 3.99, 3), ("Banana Pudding", 5.99, 4),
    ],
    11: [  # Salad Station
        ("Greek Salad", 11.99, 6), ("Cobb Salad", 13.99, 6),
        ("Caesar Salad", 10.99, 6), ("Asian Salad", 12.99, 6),
        ("Soup of the Day", 5.99, 7), ("Fresh Juice", 5.99, 5),
        ("Protein Add-on", 4.99, 2), ("Dressing", 0.99, 3),
    ],
    12: [  # Noodle Nirvana
        ("Pad Thai", 14.99, 10), ("Singapore Noodles", 13.99, 10),
        ("Dan Dan Noodles", 12.99, 10), ("Udon Stir Fry", 14.99, 10),
        ("Crab Rangoon", 7.99, 1), ("Pot Stickers", 6.99, 1),
        ("Bubble Tea", 5.99, 5), ("Mochi", 4.99, 4),
    ],
    13: [  # Fried Chicken Co
        ("2pc Chicken", 9.99, 2), ("3pc Chicken", 12.99, 2),
        ("Chicken Sandwich", 10.99, 8), ("Tenders", 11.99, 2),
        ("Mashed Potatoes", 3.99, 3), ("Biscuit", 2.49, 3),
        ("Honey Butter", 0.99, 3), ("Sweet Tea", 2.99, 5),
    ],
    14: [  # Greek Gods
        ("Souvlaki Plate", 15.99, 2), ("Moussaka", 16.99, 2),
        ("Gyro Wrap", 12.99, 8), ("Spanakopita", 8.99, 1),
        ("Greek Salad", 9.99, 6), ("Tzatziki", 4.99, 1),
        ("Baklava", 5.99, 4), ("Greek Coffee", 3.99, 5),
    ],
    15: [  # Thai Street
        ("Pad Thai", 14.99, 10), ("Green Curry", 15.99, 2),
        ("Massaman Curry", 16.99, 2), ("Tom Yum Soup", 8.99, 7),
        ("Mango Sticky Rice", 7.99, 4), ("Thai Iced Tea", 4.99, 5),
        ("Satay Skewers", 9.99, 1), ("Papaya Salad", 8.99, 6),
    ],
    16: [  # Breakfast Club
        ("Pancakes", 10.99, 2), ("Eggs Benedict", 14.99, 2),
        ("Avocado Toast", 11.99, 2), ("Breakfast Burrito", 12.99, 2),
        ("Hash Browns", 4.99, 3), ("Fresh Fruit", 5.99, 3),
        ("Orange Juice", 3.99, 5), ("Coffee", 2.99, 5),
    ],
    17: [  # Smoothie Bowl
        ("Acai Bowl", 12.99, 2), ("Pitaya Bowl", 12.99, 2),
        ("Green Smoothie", 8.99, 5), ("Protein Shake", 9.99, 5),
        ("Granola Add-on", 2.99, 3), ("Nut Butter", 1.99, 3),
        ("Fresh Berries", 3.99, 3), ("Coconut Water", 4.99, 5),
    ],
    18: [  # Ramen House
        ("Tonkotsu Ramen", 15.99, 7), ("Miso Ramen", 14.99, 7),
        ("Shoyu Ramen", 14.99, 7), ("Spicy Ramen", 15.99, 7),
        ("Gyoza", 7.99, 1), ("Karaage", 8.99, 1),
        ("Sake", 8.99, 5), ("Matcha", 4.99, 5),
    ],
    19: [  # Soul Food Kitchen
        ("Fried Catfish", 16.99, 2), ("Smothered Chicken", 15.99, 2),
        ("Oxtails", 21.99, 2), ("Meatloaf", 14.99, 2),
        ("Collard Greens", 4.99, 3), ("Candied Yams", 4.99, 3),
        ("Cornbread", 2.99, 3), ("Sweet Potato Pie", 5.99, 4),
    ],
    20: [  # Vegan Vibes
        ("Buddha Bowl", 14.99, 2), ("Vegan Burger", 13.99, 2),
        ("Cauliflower Tacos", 12.99, 2), ("Jackfruit Sandwich", 13.99, 8),
        ("Kale Chips", 5.99, 1), ("Coconut Yogurt", 6.99, 4),
        ("Kombucha", 4.99, 5), ("Date Balls", 5.99, 4),
    ],
}


def generate_items(brands: List[Brand]) -> List[Item]:
    """Generate all menu items from brand definitions."""
    items = []
    item_id = 1
    for brand in brands:
        brand_items = ITEMS_BY_BRAND.get(brand.id, [])
        for name, price, category_id in brand_items:
            items.append(Item(
                id=item_id,
                brand_id=brand.id,
                name=name,
                price=price,
                category_id=category_id,
            ))
            item_id += 1
    return items


def save_dimensions(config: GeneratorConfig) -> dict:
    """Generate and save all dimension tables to parquet files."""
    output_dir = Path(config.output_dir) / "dimensions"
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(config.seed)
    results = {}

    # Categories
    categories_table = pa.table({
        "id": [c.id for c in CATEGORIES],
        "name": [c.name for c in CATEGORIES],
    })
    categories_path = output_dir / "categories.parquet"
    pq.write_table(categories_table, categories_path)
    results["categories"] = len(CATEGORIES)

    # Brands
    brands_table = pa.table({
        "id": [b.id for b in BRANDS],
        "name": [b.name for b in BRANDS],
        "cuisine_type": [b.cuisine_type for b in BRANDS],
        "avg_prep_time_mins": [b.avg_prep_time_mins for b in BRANDS],
        "momentum": [b.momentum for b in BRANDS],
    })
    brands_path = output_dir / "brands.parquet"
    pq.write_table(brands_table, brands_path)
    results["brands"] = len(BRANDS)

    # Items
    items = generate_items(BRANDS)
    items_table = pa.table({
        "id": [i.id for i in items],
        "brand_id": [i.brand_id for i in items],
        "name": [i.name for i in items],
        "price": [i.price for i in items],
        "category_id": [i.category_id for i in items],
    })
    items_path = output_dir / "items.parquet"
    pq.write_table(items_table, items_path)
    results["items"] = len(items)

    # Locations
    locations_table = pa.table({
        "id": [loc.id for loc in config.locations],
        "city": [loc.city for loc in config.locations],
        "lat": [loc.lat for loc in config.locations],
        "lon": [loc.lon for loc in config.locations],
        "lat_min": [loc.lat_range[0] for loc in config.locations],
        "lat_max": [loc.lat_range[1] for loc in config.locations],
        "lon_min": [loc.lon_range[0] for loc in config.locations],
        "lon_max": [loc.lon_range[1] for loc in config.locations],
    })
    locations_path = output_dir / "locations.parquet"
    pq.write_table(locations_table, locations_path)
    results["locations"] = len(config.locations)

    return results


def get_brands() -> List[Brand]:
    """Return list of all brands."""
    return BRANDS


def get_items() -> List[Item]:
    """Return list of all items."""
    return generate_items(BRANDS)


def get_categories() -> List[Category]:
    """Return list of all categories."""
    return CATEGORIES
