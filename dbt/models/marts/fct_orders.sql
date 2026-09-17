-- Order-level fact table (grain: one row per order).
-- Items and payments are aggregated to order level BEFORE joining, to avoid fan-out double counting.

with orders as (

    select * from {{ ref('stg_orders') }}

),

items_per_order as (

    select
        order_id,
        count(*)                  as item_count,
        sum(price)                as items_value,
        sum(freight_value)        as freight_value,
        sum(item_total)           as order_total,
        bool_or(is_negative_price) as has_negative_price
    from {{ ref('stg_order_items') }}
    group by order_id

),

payments_per_order as (

    select
        order_id,
        count(*)                        as payment_count,
        sum(payment_value)              as total_paid,
        bool_or(is_unknown_payment_type) as has_unknown_payment_type
    from {{ ref('stg_order_payments') }}
    group by order_id

),

customers as (

    select customer_id, customer_unique_id, state
    from {{ ref('stg_customers') }}

),

joined as (

    select
        o.order_id,
        o.customer_id,
        c.customer_unique_id,
        c.state                                        as customer_state,
        o.order_status,
        o.purchased_at,
        o.purchased_at::date                           as order_date,
        o.delivered_to_customer_at,
        o.estimated_delivery_at,

        coalesce(i.item_count, 0)                      as item_count,
        coalesce(i.items_value, 0)                     as items_value,
        coalesce(i.freight_value, 0)                   as freight_value,
        coalesce(i.order_total, 0)                     as order_total,
        coalesce(p.payment_count, 0)                   as payment_count,
        coalesce(p.total_paid, 0)                      as total_paid,

        coalesce(i.has_negative_price, false)          as has_negative_price,
        coalesce(p.has_unknown_payment_type, false)    as has_unknown_payment_type,
        o.is_missing_customer,
        o.source_system
    from orders as o
    left join customers as c
        on o.customer_id = c.customer_id
    left join items_per_order as i
        on o.order_id = i.order_id
    left join payments_per_order as p
        on o.order_id = p.order_id

)

select
    *,
    total_paid - order_total as payment_gap,

    -- Delivery metrics are only meaningful once the order reached the customer
    case
        when delivered_to_customer_at is not null
        then round((extract(epoch from delivered_to_customer_at - purchased_at) / 86400)::numeric, 1)
    end as delivery_days,

    case
        when delivered_to_customer_at is not null
        then delivered_to_customer_at::date > estimated_delivery_at::date
    end as is_late_delivery,

    (
        not has_negative_price
        and not has_unknown_payment_type
        and not is_missing_customer
        and item_count > 0
        and order_status not in ('canceled', 'unavailable')
    ) as is_valid_for_revenue
from joined