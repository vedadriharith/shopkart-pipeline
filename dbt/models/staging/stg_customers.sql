-- Staging model for customers. Note: customer_id is issued per order in Olist;
-- customer_unique_id identifies the real person across orders.

with source as (

    select * from {{ source('bronze', 'customers') }}

)

select
    trim(customer_id)                                 as customer_id,
    trim(customer_unique_id)                          as customer_unique_id,
    lpad(trim(customer_zip_code_prefix), 5, '0')      as zip_code_prefix,
    initcap(trim(customer_city))                      as city,
    upper(trim(customer_state))                       as state,
    _ingested_at::timestamptz                         as ingested_at,
    _batch_id                                         as batch_id
from source