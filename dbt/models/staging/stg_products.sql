-- Staging model for products: translates Portuguese category names to English,
-- fixes misspelled source column names, and casts dimensions to numbers.

with products as (

    select * from {{ source('bronze', 'products') }}

),

translations as (

    select
        trim(product_category_name)          as category_name_pt,
        trim(product_category_name_english)  as category_name_en
    from {{ source('bronze', 'product_category_translation') }}

)

select
    trim(p.product_id)                                            as product_id,
    coalesce(t.category_name_en, trim(p.product_category_name), 'unknown') as category,
    trim(p.product_category_name)                                 as category_name_pt,
    p.product_category_name is not null
        and t.category_name_en is null                            as is_missing_translation,
    nullif(trim(p.product_name_lenght), '')::integer              as name_length,
    nullif(trim(p.product_description_lenght), '')::integer       as description_length,
    nullif(trim(p.product_photos_qty), '')::integer               as photos_qty,
    nullif(trim(p.product_weight_g), '')::integer                 as weight_g,
    nullif(trim(p.product_length_cm), '')::integer                as length_cm,
    nullif(trim(p.product_height_cm), '')::integer                as height_cm,
    nullif(trim(p.product_width_cm), '')::integer                 as width_cm,
    p._ingested_at::timestamptz                                   as ingested_at,
    p._batch_id                                                   as batch_id
from products as p
left join translations as t
    on trim(p.product_category_name) = t.category_name_pt