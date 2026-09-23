-- Item-level fact table (grain: one row per order_id + order_item_id), built incrementally.
-- Each run only processes rows ingested after the current watermark, minus a lookback window
-- for late-arriving data. delete+insert on the unique key keeps overlapping rows from duplicating.

{{
    config(
        materialized='incremental',
        unique_key=['order_id', 'order_item_id'],
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}

with items as (

    select * from {{ ref('stg_order_items') }}

    {% if is_incremental() %}
    where ingested_at > (
        select coalesce(max(ingested_at), '1900-01-01'::timestamptz)
               - interval '{{ var("incremental_lookback_hours") }} hours'
        from {{ this }}
    )
    {% endif %}

)

select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_at,
    price,
    freight_value,
    item_total,
    is_negative_price,
    source_system,
    ingested_at,
    source_file,
    current_timestamp as processed_at
from items