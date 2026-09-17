-- Customer dimension (grain: one row per real person, customer_unique_id).
-- Location comes from the customer's most recent order; metrics come from fct_orders.

with customer_orders as (

    select
        customer_unique_id,
        customer_id,
        order_id,
        purchased_at,
        order_total,
        is_valid_for_revenue
    from {{ ref('fct_orders') }}
    where customer_unique_id is not null

),

latest_location as (

    select
        co.customer_unique_id,
        c.city,
        c.state,
        c.zip_code_prefix,
        row_number() over (
            partition by co.customer_unique_id
            order by co.purchased_at desc, co.order_id desc
        ) as row_num
    from customer_orders as co
    inner join {{ ref('stg_customers') }} as c
        on co.customer_id = c.customer_id

),

order_stats as (

    select
        customer_unique_id,
        count(*)                                                  as total_orders,
        count(*) filter (where is_valid_for_revenue)              as valid_orders,
        min(purchased_at)                                         as first_order_at,
        max(purchased_at)                                         as last_order_at,
        coalesce(sum(order_total) filter (where is_valid_for_revenue), 0) as lifetime_value
    from customer_orders
    group by customer_unique_id

)

select
    s.customer_unique_id,
    l.city,
    l.state,
    l.zip_code_prefix,
    s.total_orders,
    s.valid_orders,
    s.first_order_at,
    s.last_order_at,
    s.lifetime_value,
    case
        when s.valid_orders > 0 then round(s.lifetime_value / s.valid_orders, 2)
    end                                  as avg_order_value,
    s.total_orders > 1                   as is_repeat_customer,
    case
        when s.lifetime_value >= 1000 then 'high'
        when s.lifetime_value >= 200  then 'medium'
        when s.lifetime_value > 0     then 'low'
        else 'no_valid_orders'
    end                                  as value_segment
from order_stats as s
left join latest_location as l
    on s.customer_unique_id = l.customer_unique_id
   and l.row_num = 1