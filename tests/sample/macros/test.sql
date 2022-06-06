/*
Column should be the regelar expression `pattern`
```dbt
arguments:
  - name: "pattern"
    type: "string"
    description: "a regular expresion"
```
*/
{% test regexp(model, column_name, pattern) %}
with validation as (
    select
        {{ column_name }} as target_field
    from {{ model }}
),
validation_errors as (
    select target_field
    from validation
    where not regexp_like(target_field,'{{ pattern }}')
)
select * from validation_errors
{% endtest %}
