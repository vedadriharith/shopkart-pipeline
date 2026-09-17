-- Daily business KPIs (grain: one row per order_date).

select
    order_date,
    count(*)                                                        as total_orders,
    count(*) filter (where is_valid_for_revenue)                    as valid_orders,
    coalesce(sum(order_total) filter (where is_valid_for_revenue), 0)   as revenue,
    coalesce(sum(items_value) filter (where is_valid_for_revenue), 0)   as items_revenue,
    coalesce(sum(freight_value) filter (where is_valid_for_revenue), 0) as freight_revenue,
    round(
        sum(order_total) filter (where is_valid_for_revenue)
        / nullif(count(*) filter (where is_valid_for_revenue), 0), 2
    )                                                               as avg_order_value,
    count(distinct customer_unique_id) filter (where is_valid_for_revenue) as unique_customers,
    count(*) filter (where delivered_to_customer_at is not null)    as delivered_orders,
    count(*) filter (where is_late_delivery)                        as late_deliveries,
    round(
        100.0 * count(*) filter (where is_late_delivery)
        / nullif(count(*) filter (where delivered_to_customer_at is not null), 0), 2
    )                                                               as late_delivery_pct
from {{ ref('fct_orders') }}
group by order_date