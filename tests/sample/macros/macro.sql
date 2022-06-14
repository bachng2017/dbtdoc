/*
The first macro
```dbt
arguments:
  - name: alias
    type: string
    description: an alias
```
*/
{%- macro macro_one(alias) -%}
select 1 as {{ alias }}
{%- endmacro -%}

/*
The second macro
*/
{%- macro macro_two(alias) -%}
select 1 as {{ alias }}
{%- endmacro -%}


{%- macro macro_no_comment() -%}
select 1 as id
{%- endmacro -%}

