-- Staging model for orders: unions historical Olist and live ShopKart orders,
-- standardises text and timestamps, and removes duplicate order rows.

with olist_orders as (

    select
        order_id,
        customer_id,
        order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date,
        'olist' as source_system,
        _ingested_at,
        _source_file,
        _batch_id
    from {{ source('bronze', 'orders') }}

),

live_orders as (

    select
        order_id,
        customer_id,
        order_status,
        order_purchase_timestamp,
        order_approved_at,
        order_delivered_carrier_date,
        order_delivered_customer_date,
        order_estimated_delivery_date,
        'live' as source_system,
        _ingested_at,
        _source_file,
        _batch_id
    from {{ source('bronze', 'live_orders') }}

),

unioned as (

    select * from olist_orders
    union all
    select * from live_orders

),

cleaned as (

    select
        trim(order_id)                                   as order_id,
        nullif(trim(customer_id), '')                    as customer_id,
        lower(trim(order_status))                        as order_status,
        {{ parse_ts('order_purchase_timestamp') }}       as purchased_at,
        {{ parse_ts('order_approved_at') }}              as approved_at,
        {{ parse_ts('order_delivered_carrier_date') }}   as delivered_to_carrier_at,
        {{ parse_ts('order_delivered_customer_date') }}  as delivered_to_customer_at,
        {{ parse_ts('order_estimated_delivery_date') }}  as estimated_delivery_at,
        nullif(trim(customer_id), '') is null            as is_missing_customer,
        source_system,
        _ingested_at::timestamptz                        as ingested_at,
        _source_file                                     as source_file,
        _batch_id                                        as batch_id
    from unioned

),

deduplicated as (

    -- Keep only the most recently ingested copy of each order_id
    select
        *,
        row_number() over (
            partition by order_id
            order by ingested_at desc, source_file desc
        ) as row_num
    from cleaned

)

select
    order_id,
    customer_id,
    order_status,
    purchased_at,
    approved_at,
    delivered_to_carrier_at,
    delivered_to_customer_at,
    estimated_delivery_at,
    is_missing_customer,
    source_system,
    ingested_at,
    source_file,
    batch_id
from deduplicated
where row_num = 1