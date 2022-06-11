
-- Use the `ref` function to select from other models
/*
The second model has no document for column
*/
select *
from {{ ref('model01') }}
where id = 1
