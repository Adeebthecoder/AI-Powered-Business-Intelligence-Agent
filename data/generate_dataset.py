"""
generate_dataset.py
-------------------
Creates the sample dataset used in the demo: indian_retail_sales.csv

It makes about 10,000 retail orders for an imaginary Indian retail company
for the years 2023, 2024 and 2025. All amounts are in Indian Rupees (INR).

The data is random, but the random seed is fixed, so running this script
again always gives exactly the same file.

Patterns that are built in on purpose (so the insights are interesting):
  1. Festive season spikes: many more orders in October and November.
  2. Steady yearly growth: each year has more orders than the year before.
  3. One weak region: East has few orders and does not grow.
  4. One problem category: Furniture gets heavy discounts, so its profit is poor.

Mess that is added on purpose (so the cleaning step has something to fix):
  - missing values in a few columns
  - duplicate rows
  - three different date formats
  - inconsistent capital letters and extra spaces

How to run:
    python generate_dataset.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42                      # fixed seed, so the output never changes
TARGET_ORDERS = 10_000         # number of real orders (before duplicates)
OUTPUT_FILE = Path(__file__).parent / "indian_retail_sales.csv"

rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------------------
# 1. Reference data: regions, cities, products
# ---------------------------------------------------------------------------

# region -> list of (state, city)
LOCATIONS = {
    "North": [("Delhi", "New Delhi"), ("Uttar Pradesh", "Lucknow"), ("Uttar Pradesh", "Noida"),
              ("Uttar Pradesh", "Kanpur"), ("Punjab", "Ludhiana"), ("Haryana", "Gurugram"),
              ("Rajasthan", "Jaipur")],
    "South": [("Karnataka", "Bengaluru"), ("Karnataka", "Mysuru"), ("Tamil Nadu", "Chennai"),
              ("Tamil Nadu", "Coimbatore"), ("Telangana", "Hyderabad"), ("Kerala", "Kochi")],
    "West": [("Maharashtra", "Mumbai"), ("Maharashtra", "Pune"), ("Maharashtra", "Nagpur"),
             ("Gujarat", "Ahmedabad"), ("Gujarat", "Surat"), ("Goa", "Panaji")],
    "East": [("West Bengal", "Kolkata"), ("Odisha", "Bhubaneswar"), ("Bihar", "Patna"),
             ("Assam", "Guwahati"), ("Jharkhand", "Ranchi")],
}

# Share of orders per region in the first year. East is the weak region.
REGION_SHARE = {"West": 0.31, "South": 0.29, "North": 0.27, "East": 0.13}

# Yearly growth in order volume per region. East stays flat.
REGION_GROWTH = {"West": 1.19, "South": 1.20, "North": 1.17, "East": 1.00}

# (category, sub_category, product_name, base_price_inr, cost_as_share_of_price)
PRODUCTS = [
    ("Electronics", "Mobiles", "Smartphone 5G 128GB", 18999, 0.80),
    ("Electronics", "Mobiles", "Smartphone 4G 64GB", 9499, 0.80),
    ("Electronics", "Laptops", "Laptop 14 inch i5", 52990, 0.83),
    ("Electronics", "Laptops", "Laptop 15 inch Ryzen 5", 46990, 0.83),
    ("Electronics", "Audio", "Wireless Earbuds", 1999, 0.62),
    ("Electronics", "Audio", "Bluetooth Speaker", 2499, 0.62),
    ("Electronics", "Accessories", "Power Bank 10000mAh", 1199, 0.58),
    ("Electronics", "Accessories", "USB-C Fast Charger", 699, 0.55),
    ("Fashion", "Men's Wear", "Cotton Formal Shirt", 1299, 0.52),
    ("Fashion", "Men's Wear", "Slim Fit Jeans", 1799, 0.52),
    ("Fashion", "Women's Wear", "Printed Kurti", 999, 0.50),
    ("Fashion", "Women's Wear", "Silk Blend Saree", 3499, 0.55),
    ("Fashion", "Footwear", "Running Shoes", 2499, 0.56),
    ("Fashion", "Footwear", "Leather Sandals", 1199, 0.54),
    ("Home & Kitchen", "Cookware", "Non-Stick Cookware Set", 2299, 0.60),
    ("Home & Kitchen", "Cookware", "Pressure Cooker 5L", 1899, 0.62),
    ("Home & Kitchen", "Appliances", "Mixer Grinder 750W", 3499, 0.66),
    ("Home & Kitchen", "Appliances", "Electric Kettle 1.5L", 899, 0.60),
    ("Home & Kitchen", "Home Decor", "Wall Clock", 599, 0.48),
    ("Home & Kitchen", "Home Decor", "Cotton Bedsheet Set", 1499, 0.52),
    ("Furniture", "Chairs", "Ergonomic Office Chair", 8999, 0.70),
    ("Furniture", "Chairs", "Plastic Dining Chair", 1499, 0.68),
    ("Furniture", "Tables", "Study Table", 5499, 0.70),
    ("Furniture", "Tables", "Coffee Table", 4299, 0.70),
    ("Furniture", "Storage", "3-Door Wardrobe", 16999, 0.72),
    ("Furniture", "Storage", "Bookshelf", 3999, 0.70),
    ("Grocery", "Staples", "Basmati Rice 5kg", 649, 0.80),
    ("Grocery", "Staples", "Whole Wheat Atta 10kg", 479, 0.82),
    ("Grocery", "Snacks", "Namkeen Combo Pack", 299, 0.72),
    ("Grocery", "Beverages", "Assam Tea 1kg", 549, 0.74),
    ("Grocery", "Beverages", "Instant Coffee 200g", 449, 0.74),
    ("Beauty & Personal Care", "Skincare", "Sunscreen SPF 50", 499, 0.45),
    ("Beauty & Personal Care", "Skincare", "Face Wash Combo", 349, 0.45),
    ("Beauty & Personal Care", "Haircare", "Herbal Shampoo 650ml", 399, 0.48),
    ("Beauty & Personal Care", "Haircare", "Hair Oil 500ml", 299, 0.48),
]

# How often each category is ordered (relative weights).
CATEGORY_WEIGHT = {
    "Electronics": 0.22, "Fashion": 0.22, "Home & Kitchen": 0.17,
    "Furniture": 0.10, "Grocery": 0.17, "Beauty & Personal Care": 0.12,
}

SEGMENTS = ["Consumer", "Corporate", "Small Business"]
SEGMENT_SHARE = [0.60, 0.25, 0.15]

PAYMENT_MODES = ["UPI", "Credit Card", "Debit Card", "Net Banking", "Cash on Delivery", "Wallet"]
PAYMENT_SHARE = [0.42, 0.18, 0.12, 0.08, 0.15, 0.05]

# Month seasonality (1.0 = normal month). October and November are festive
# months (Navratri, Dussehra, Diwali), so they get a big boost.
MONTH_WEIGHT = {1: 1.05, 2: 0.85, 3: 0.95, 4: 0.90, 5: 0.92, 6: 0.85,
                7: 0.95, 8: 1.08, 9: 1.00, 10: 1.75, 11: 1.60, 12: 1.15}

YEARS = [2023, 2024, 2025]


# ---------------------------------------------------------------------------
# 2. Build the clean data
# ---------------------------------------------------------------------------

def build_customers(n_customers=2500):
    """Each customer has a fixed segment and a fixed home city."""
    regions = rng.choice(list(REGION_SHARE), size=n_customers, p=list(REGION_SHARE.values()))
    rows = []
    for i, region in enumerate(regions, start=1):
        state, city = LOCATIONS[region][rng.integers(len(LOCATIONS[region]))]
        rows.append({
            "customer_id": f"CUST-{i:04d}",
            "customer_segment": rng.choice(SEGMENTS, p=SEGMENT_SHARE),
            "region": region, "state": state, "city": city,
        })
    return pd.DataFrame(rows)


def orders_per_region_month():
    """Work out how many orders each (year, month, region) should get."""
    weights = {}
    for y_index, year in enumerate(YEARS):
        for month in range(1, 13):
            for region, share in REGION_SHARE.items():
                growth = REGION_GROWTH[region] ** y_index
                weights[(year, month, region)] = share * growth * MONTH_WEIGHT[month]
    total = sum(weights.values())
    return {key: int(round(TARGET_ORDERS * w / total)) for key, w in weights.items()}


def pick_discount(category, month):
    """Discount as a fraction (0.10 means 10%)."""
    if category == "Furniture":
        # Furniture is the problem category: very heavy discounts.
        discount = rng.choice([0.20, 0.30, 0.35, 0.40, 0.45], p=[0.15, 0.25, 0.25, 0.20, 0.15])
    else:
        discount = rng.choice([0.0, 0.05, 0.10, 0.15, 0.20], p=[0.35, 0.25, 0.20, 0.12, 0.08])
        if month in (10, 11) and rng.random() < 0.5:
            discount += 0.05       # festive offers
    return round(float(discount), 2)


def build_orders():
    customers = build_customers()
    customers_by_region = {r: g.reset_index(drop=True) for r, g in customers.groupby("region")}

    categories = list(CATEGORY_WEIGHT)
    category_p = list(CATEGORY_WEIGHT.values())
    products_by_category = {c: [p for p in PRODUCTS if p[0] == c] for c in categories}

    rows = []
    for (year, month, region), n_orders in orders_per_region_month().items():
        days_in_month = pd.Period(f"{year}-{month:02d}").days_in_month
        region_customers = customers_by_region[region]
        for _ in range(n_orders):
            customer = region_customers.iloc[rng.integers(len(region_customers))]
            category = rng.choice(categories, p=category_p)
            _, sub_category, product_name, base_price, cost_share = \
                products_by_category[category][rng.integers(len(products_by_category[category]))]

            # Small price changes over time and between orders.
            unit_price = round(base_price * rng.normal(1.0, 0.04) * (1.03 ** YEARS.index(year)), 0)
            unit_cost = base_price * cost_share * (1.03 ** YEARS.index(year))

            if category == "Grocery":
                quantity = int(rng.integers(1, 7))
            elif category in ("Electronics", "Furniture"):
                quantity = int(rng.choice([1, 2, 3], p=[0.75, 0.20, 0.05]))
            else:
                quantity = int(rng.choice([1, 2, 3, 4], p=[0.50, 0.30, 0.15, 0.05]))
            # Corporate customers buy in larger quantities.
            if customer["customer_segment"] == "Corporate" and rng.random() < 0.4:
                quantity += int(rng.integers(1, 4))

            discount = pick_discount(category, month)
            revenue = round(quantity * unit_price * (1 - discount), 2)
            cost = round(quantity * unit_cost, 2)
            profit = round(revenue - cost, 2)

            rows.append({
                "order_date": pd.Timestamp(year, month, int(rng.integers(1, days_in_month + 1))),
                "customer_id": customer["customer_id"],
                "customer_segment": customer["customer_segment"],
                "region": region, "state": customer["state"], "city": customer["city"],
                "product_category": category, "sub_category": sub_category,
                "product_name": product_name,
                "quantity": quantity, "unit_price": unit_price, "discount": discount,
                "revenue": revenue, "cost": cost, "profit": profit,
                "payment_mode": rng.choice(PAYMENT_MODES, p=PAYMENT_SHARE),
            })

    df = pd.DataFrame(rows).sort_values("order_date").reset_index(drop=True)
    # Order ids run in date order, for example ORD-2023-00001.
    df.insert(0, "order_id", [f"ORD-{d.year}-{i:05d}" for i, d in enumerate(df["order_date"], start=1)])
    return df


# ---------------------------------------------------------------------------
# 3. Add mess on purpose
# ---------------------------------------------------------------------------

def add_mess(df):
    df = df.copy()
    n = len(df)

    # (a) Mixed date formats: most ISO, some Indian dd/mm/yyyy, some dd-Mon-yyyy.
    fmt_choice = rng.choice(["iso", "slash", "text"], size=n, p=[0.85, 0.10, 0.05])
    formats = {"iso": "%Y-%m-%d", "slash": "%d/%m/%Y", "text": "%d-%b-%Y"}
    df["order_date"] = [d.strftime(formats[f]) for d, f in zip(df["order_date"], fmt_choice)]

    # (b) Inconsistent capital letters and stray spaces in some text columns.
    def scramble(value):
        style = rng.integers(3)
        if style == 0:
            return value.lower()
        if style == 1:
            return value.upper()
        return f" {value} "

    for column, share in [("region", 0.03), ("product_category", 0.03), ("payment_mode", 0.02)]:
        idx = rng.choice(n, size=int(n * share), replace=False)
        df.loc[idx, column] = [scramble(v) for v in df.loc[idx, column]]

    # (c) Missing values in a few columns.
    for column, share in [("customer_segment", 0.015), ("payment_mode", 0.010),
                          ("city", 0.005), ("discount", 0.010)]:
        idx = rng.choice(n, size=int(n * share), replace=False)
        df.loc[idx, column] = np.nan

    # (d) Duplicate rows: copy about 1.2% of rows and mix them back in.
    duplicates = df.sample(n=int(n * 0.012), random_state=SEED)
    df = pd.concat([df, duplicates], ignore_index=True)
    df = df.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    return df


if __name__ == "__main__":
    clean = build_orders()
    messy = add_mess(clean)
    messy.to_csv(OUTPUT_FILE, index=False)
    print(f"Real orders       : {len(clean):,}")
    print(f"Rows written      : {len(messy):,} (includes duplicate rows added on purpose)")
    print(f"Total revenue     : INR {clean['revenue'].sum():,.0f}")
    print(f"Saved to          : {OUTPUT_FILE}")
    print()
    print("Revenue by year:")
    print(clean.groupby(clean["order_date"].dt.year)["revenue"].sum().round(0).to_string())
    print()
    print("Revenue and profit by region:")
    print(clean.groupby("region")[["revenue", "profit"]].sum().round(0).to_string())
    print()
    print("Revenue, profit and average discount by category:")
    summary = clean.groupby("product_category").agg(
        revenue=("revenue", "sum"), profit=("profit", "sum"), avg_discount=("discount", "mean"))
    print(summary.round(2).to_string())
