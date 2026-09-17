-- Staging model for sellers.

with source as (

    select * from {{ source('bronze', 'sellers') }}

)

select
    trim(seller_id)                                 as seller_id,
    lpad(trim(seller_zip_code_prefix), 5, '0')      as zip_code_prefix,
    initcap(trim(seller_city))                      as city,
    upper(trim(seller_state))                       as state,
    _ingested_at::timestamptz                       as ingested_at,
    _batch_id                                       as batch_id
from source