-- Reconciliation: valid revenue must be identical across every gold model that reports it.
-- Returns a row (and fails the build) if any total drifts by more than one cent.

with totals as (

    select
        (select coalesce(sum(order_total) filter (where is_valid_for_revenue), 0)
           from {{ ref('fct_orders') }})                  as fct_orders_revenue,
        (select coalesce(sum(revenue), 0)
           from {{ ref('mart_daily_revenue') }})          as daily_revenue,
        (select coalesce(sum(total_revenue), 0)
           from {{ ref('mart_category_performance') }})   as category_revenue,
        (select coalesce(sum(lifetime_value), 0)
           from {{ ref('dim_customers') }})               as customer_revenue

)

select *
from totals
where abs(fct_orders_revenue - daily_revenue)    > 0.01
   or abs(fct_orders_revenue - category_revenue) > 0.01
   or abs(fct_orders_revenue - customer_revenue) > 0.01