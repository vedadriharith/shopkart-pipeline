-- Staging model for order items: unions historical and live items,
-- casts numeric and timestamp fields, flags negative prices, and dedups on the item grain.

with unioned as (

    select
        order_id, order_item_id, product_id, seller_id,
        shipping_limit_date, price, freight_value,
        'olist' as source_system, _ingested_at, _source_file, _batch_id
    from {{ source('bronze', 'order_items') }}

    union all

    select
        order_id, order_item_id, product_id, seller_id,
        shipping_limit_date, price, freight_value,
        'live' as source_system, _ingested_at, _source_file, _batch_id
    from {{ source('bronze', 'live_order_items') }}

),

cleaned as (

    select
        trim(order_id)                                  as order_id,
        nullif(trim(order_item_id), '')::integer        as order_item_id,
        nullif(trim(product_id), '')                    as product_id,
        nullif(trim(seller_id), '')                     as seller_id,
        {{ parse_ts('shipping_limit_date') }}           as shipping_limit_at,
        nullif(trim(price), '')::numeric(12, 2)         as price,
        nullif(trim(freight_value), '')::numeric(12, 2) as freight_value,
        source_system,
        _ingested_at::timestamptz                       as ingested_at,
        _source_file                                    as source_file,
        _batch_id                                       as batch_id
    from unioned

),

deduplicated as (

    -- Grain: one row per (order_id, order_item_id)
    select
        *,
        row_number() over (
            partition by order_id, order_item_id
            order by ingested_at desc, source_file desc
        ) as row_num
    from cleaned

)

select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_at,
    price,
    freight_value,
    price + freight_value  as item_total,
    price < 0              as is_negative_price,
    source_system,
    ingested_at,
    source_file,
    batch_id
from deduplicated
where row_num = 1