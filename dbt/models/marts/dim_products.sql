-- Product dimension (grain: one row per product_id) with derived size attributes.

select
    product_id,
    category,
    category_name_pt,
    is_missing_translation,
    photos_qty,
    weight_g,
    length_cm,
    height_cm,
    width_cm,
    length_cm * height_cm * width_cm as volume_cm3,
    case
        when weight_g is null  then 'unknown'
        when weight_g < 500    then 'small'
        when weight_g < 5000   then 'medium'
        else 'large'
    end as size_band
from {{ ref('stg_products') }}