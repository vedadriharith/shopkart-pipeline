-- Staging model for order payments: unions historical and live payments,
-- standardises payment type, flags types outside the accepted list, and dedups on the payment grain.

with unioned as (

    select
        order_id, payment_sequential, payment_type,
        payment_installments, payment_value,
        'olist' as source_system, _ingested_at, _source_file, _batch_id
    from {{ source('bronze', 'order_payments') }}

    union all

    select
        order_id, payment_sequential, payment_type,
        payment_installments, payment_value,
        'live' as source_system, _ingested_at, _source_file, _batch_id
    from {{ source('bronze', 'live_order_payments') }}

),

cleaned as (

    select
        trim(order_id)                                       as order_id,
        nullif(trim(payment_sequential), '')::integer        as payment_sequential,
        lower(trim(payment_type))                            as payment_type,
        nullif(trim(payment_installments), '')::integer      as payment_installments,
        nullif(trim(payment_value), '')::numeric(12, 2)      as payment_value,
        source_system,
        _ingested_at::timestamptz                            as ingested_at,
        _source_file                                         as source_file,
        _batch_id                                            as batch_id
    from unioned

),

deduplicated as (

    -- Grain: one row per (order_id, payment_sequential)
    select
        *,
        row_number() over (
            partition by order_id, payment_sequential
            order by ingested_at desc, source_file desc
        ) as row_num
    from cleaned

)

select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value,
    payment_type not in (
        {%- for payment_type in var('accepted_payment_types') %}
        '{{ payment_type }}'{% if not loop.last %},{% endif %}
        {%- endfor %}
    ) as is_unknown_payment_type,
    source_system,
    ingested_at,
    source_file,
    batch_id
from deduplicated
where row_num = 1