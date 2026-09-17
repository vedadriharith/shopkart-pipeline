{#- Fails for every row where a boolean quality flag column is true. -#}
{% test not_flagged(model, column_name) %}

select *
from {{ model }}
where {{ column_name }} = true

{% endtest %}