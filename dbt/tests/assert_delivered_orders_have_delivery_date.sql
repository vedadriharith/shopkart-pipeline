-- Business rule: an order marked as delivered must have a customer delivery timestamp.
{{ config(severity='warn') }}

select
    order_id,
    order_status,
    purchased_at,
    delivered_to_customer_at,
    source_system
from {{ ref('stg_orders') }}
where order_status = 'delivered'
  and delivered_to_customer_at is null