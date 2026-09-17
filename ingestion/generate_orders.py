"""Generate simulated new ShopKart orders as JSON Lines files in the landing zone."""

import argparse
import json
import logging
import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from db import PROJECT_ROOT, get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

LANDING_DIR = PROJECT_ROOT / "data" / "landing"
TS_FORMAT = "%Y-%m-%d %H:%M:%S"
PAYMENT_TYPES = ["credit_card", "boleto", "voucher", "debit_card"]
DIRTY_ISSUES = [
    "duplicate_order",
    "missing_customer",
    "negative_price",
    "messy_status",
    "iso_timestamp",
    "unknown_payment_type",
]


def load_reference_data(engine, sample_size: int = 5000):
    """Fetch real customer and product/seller IDs from bronze so new orders stay consistent."""
    with engine.connect() as conn:
        customers = [
            row[0]
            for row in conn.execute(
                text("SELECT customer_id FROM bronze.customers ORDER BY random() LIMIT :n"),
                {"n": sample_size},
            )
        ]
        products = [
            (row[0], row[1], float(row[2]))
            for row in conn.execute(
                text(
                    """
                    SELECT product_id, seller_id, AVG(price::numeric) AS avg_price
                    FROM bronze.order_items
                    GROUP BY product_id, seller_id
                    ORDER BY random()
                    LIMIT :n
                    """
                ),
                {"n": sample_size},
            )
        ]
    return customers, products


def build_order(customers, products, now: datetime):
    """Build one clean order with its items and a single payment."""
    order_id = uuid.uuid4().hex
    purchase_ts = now - timedelta(minutes=random.randint(30, 90))
    status = random.choices(
        ["created", "approved", "invoiced", "processing"], weights=[20, 40, 25, 15]
    )[0]
    approved_ts = None if status == "created" else purchase_ts + timedelta(minutes=random.randint(5, 25))

    order = {
        "order_id": order_id,
        "customer_id": random.choice(customers),
        "order_status": status,
        "order_purchase_timestamp": purchase_ts.strftime(TS_FORMAT),
        "order_approved_at": approved_ts.strftime(TS_FORMAT) if approved_ts else None,
        "order_delivered_carrier_date": None,
        "order_delivered_customer_date": None,
        "order_estimated_delivery_date": (purchase_ts + timedelta(days=random.randint(5, 20))).strftime(TS_FORMAT),
    }

    items = []
    order_total = 0.0
    item_count = random.choices([1, 2, 3], weights=[80, 15, 5])[0]
    for item_seq in range(1, item_count + 1):
        product_id, seller_id, base_price = random.choice(products)
        price = round(base_price * random.uniform(0.9, 1.1), 2)
        freight = round(random.uniform(5, 40), 2)
        order_total += price + freight
        items.append(
            {
                "order_id": order_id,
                "order_item_id": item_seq,
                "product_id": product_id,
                "seller_id": seller_id,
                "shipping_limit_date": (purchase_ts + timedelta(days=3)).strftime(TS_FORMAT),
                "price": price,
                "freight_value": freight,
            }
        )

    payments = [
        {
            "order_id": order_id,
            "payment_sequential": 1,
            "payment_type": random.choice(PAYMENT_TYPES),
            "payment_installments": random.randint(1, 10),
            "payment_value": round(order_total, 2),
        }
    ]
    return order, items, payments


def inject_issue(order, items, payments, purchase_ts_raw: str) -> str:
    """Corrupt a clean order in one realistic way and return the issue name."""
    issue = random.choice(DIRTY_ISSUES)
    if issue == "missing_customer":
        order["customer_id"] = None
    elif issue == "negative_price":
        items[0]["price"] = -abs(items[0]["price"])
    elif issue == "messy_status":
        order["order_status"] = f" {order['order_status'].upper()} "
    elif issue == "iso_timestamp":
        parsed = datetime.strptime(purchase_ts_raw, TS_FORMAT)
        order["order_purchase_timestamp"] = parsed.isoformat() + "Z"
    elif issue == "unknown_payment_type":
        payments[0]["payment_type"] = "UPI"
    # "duplicate_order" is handled by the caller, which appends the order twice
    return issue


def write_jsonl(entity: str, rows: list, batch_tag: str):
    """Write rows atomically: write to a temp file first, then rename it into place."""
    folder = LANDING_DIR / entity
    folder.mkdir(parents=True, exist_ok=True)
    final_path = folder / f"{entity}_{batch_tag}.jsonl"
    temp_path = folder / f"{entity}_{batch_tag}.jsonl.tmp"

    with temp_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    temp_path.replace(final_path)
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate simulated ShopKart orders.")
    parser.add_argument("--orders", type=int, default=200, help="Number of orders to generate")
    parser.add_argument("--dirty-rate", type=float, default=0.05, help="Fraction of orders with data issues")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible output")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    engine = get_engine()
    customers, products = load_reference_data(engine)
    now = datetime.now()
    batch_tag = f"{now.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"

    all_orders, all_items, all_payments = [], [], []
    issue_counts = {}

    for _ in range(args.orders):
        order, items, payments = build_order(customers, products, now)

        if random.random() < args.dirty_rate:
            issue = inject_issue(order, items, payments, order["order_purchase_timestamp"])
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
            if issue == "duplicate_order":
                all_orders.append(dict(order))

        all_orders.append(order)
        all_items.extend(items)
        all_payments.extend(payments)

    for entity, rows in (("orders", all_orders), ("order_items", all_items), ("order_payments", all_payments)):
        path = write_jsonl(entity, rows, batch_tag)
        log.info(f"Wrote {len(rows):>5} rows -> {path.relative_to(PROJECT_ROOT)}")

    log.info(f"Batch {batch_tag} done. Injected issues: {issue_counts or 'none'}")


if __name__ == "__main__":
    main()