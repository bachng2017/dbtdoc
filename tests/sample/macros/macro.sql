/*
The only one macro
```dbt
arguments:
  - name: alias
    type: string
    description: an alias
```
*/
{%- macro one_macro(alias) -%}
select 1 as {{ alias }}
{%- endmacro -%}


