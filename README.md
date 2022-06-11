# dbtdoc
Create dbt document from SQL files

## Install
```
pip install dbtdoc
```



## Features
Currently support document for following
- model
- seed
- common macro and test
- materialization

## Usage

### Prepare
dbtdoc will extract the information from SQL comment block /* */ for each macro and test.

A typical comment block will look like this:

~~~
/*
This information will be used in dbt document.
Information insides dbt block is used to create dbt yml file 
```dbt
arguments:
  - name: arg01
    type: string
    description: the first argument
```
* any thing after `dbt` block will be ignored
*/
~~~

By default, every macro, tests will be displayed in dbt document navigator. 
Remove item from document by adding following setting.

~~~
/*
this will no be displayed in dbt doc
```dbt
docs:
   show: false
```
*/
~~~

### Usage
Default syntax is below: 
```
dbtdoc [-h] [-b] [-d DOC] [-o] [-s SCHEMA] dbt_dir
```

By default `dbtdoc` will scan the `dbt_dir` and all of its sub-folder for sql file, creates 2 file `dbt_schema.yml` and `docs.md` for each folder (the names of the file could be changed by .dbtdoc)
In case `dbtdoc` found a `dbt_project.yml` in the target folder, it will only scan the folders defined by `models-path` and `macros-path` from the file

Paramaeter `-o` is used to limit `dbtdoc` only process on the target `dbt_dir` only but ignore its sub-folder.


## Configuration
Configuration file `.dbtodoc` is searched in current folder. A typical configuration file looks like this:
```.dbtdoc
schema_file: "dbt_schema.yml"
doc_file: "docs.md"
quote_string: true
```

## Other
This project is inspired by this: https://github.com/anelendata/dbt_docstring
