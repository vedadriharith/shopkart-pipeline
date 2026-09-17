{#- Parse a raw text timestamp that may be "YYYY-MM-DD HH:MI:SS" or ISO style "YYYY-MM-DDTHH:MI:SSZ". -#}
{% macro parse_ts(column_name) -%}
    nullif(replace(rtrim(trim({{ column_name }}), 'Z'), 'T', ' '), '')::timestamp
{%- endmacro %}