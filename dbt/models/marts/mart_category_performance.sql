-- Category performance (grain: one row per product category), valid orders only.
-- All joins are many-to-one from the item grain, so no fan-out.

with valid_items as (

    select
        i.order_id,
        i.product_id,
        i.price,
        i.freight_value,
        i.item_total,
        o.customer_unique_id
    from {{ ref('stg_order_items') }} as i
    inner join {{ ref('fct_orders') }} as o
        on i.order_id = o.order_id
    where o.is_valid_for_revenue

)

select
    coalesce(p.category, 'unknown')                       as category,
    count(*)                                              as units_sold,
    count(distinct v.order_id)                            as orders,
    count(distinct v.customer_unique_id)                  as customers,
    sum(v.price)                                          as items_revenue,
    sum(v.freight_value)                                  as freight_revenue,
    sum(v.item_total)                                     as total_revenue,
    round(avg(v.price), 2)                                as avg_item_price,
    round(100 * sum(v.item_total) / sum(sum(v.item_total)) over (), 2) as revenue_share_pct,
    rank() over (order by sum(v.item_total) desc)         as revenue_rank
from valid_items as v
left join {{ ref('dim_products') }} as p
    on v.product_id = p.product_id
group by coalesce(p.category, 'unknown')