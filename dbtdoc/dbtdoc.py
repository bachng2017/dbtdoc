#!/usr/bin/env python3
import argparse, datetime, logging, os, sys
from collections import defaultdict
# from collections import OrderedDict

from textwrap import indent
import yaml,re,os.path

logger = logging.getLogger(__name__)

COMMAND = "dbtdoc"
DBT_BLOCK_START_KEY = "```dbt"

# default configuration
SCHEMA_FILE = "dbt_schema.yml"
DOC_FILE = "docs.md"
QUOTE_STRING = True

class Dumper(yaml.Dumper):
    """ A workaround to indent list more friendly
        See https://github.com/yaml/pyyaml/issues/234 for details
    """
    def increase_indent(self, flow=False, *args, **kwargs):
        return super().increase_indent(flow=flow, indentless=False)

class quoted(str):
    pass


# yaml quoted string representor
def _represent_quoted(dumper, instance):
    return dumper.represent_scalar('tag:yaml.org,2002:str', instance, style='"')
# yaml.add_representer(quoted, _represent_quoted)


# yaml string representor
def _represent_str(dumper, instance):
    if "\n" in instance:
        return dumper.represent_scalar("tag:yaml.org,2002:str", instance, style="|")
    else:
        return dumper.represent_scalar("tag:yaml.org,2002:str", instance)
yaml.add_representer(str, _represent_str)


def _get_dirs(dbt_dir):
    """ Return the value of `model-paths` and `macro-path`
    """
    dbt_project_file = os.path.join(dbt_dir, "dbt_project.yml")
    if not os.path.isfile(dbt_project_file):
        print("dbt_project.yml not found in {}".format(dbt_dir))
        exit(1)
    with open(dbt_project_file, "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return config["model-paths"], config["macro-paths"]


def _read_blocks(sql_file):
    """ Extract doc, dbt block from comments
        doc block: everything from the beginning to dbt block
        dbt block: evertyhing inside ```dbt block
        everything after the dbt block is ignored by dbtdocstr
    """
    with open(sql_file, "r") as f:
        sql = f.read()
    doc_start = sql.find("/*")
    doc_end = sql.find("*/")
    doc = sql[doc_start + 2:doc_end] if doc_start > -1 else ""

    dbt = {}
    if doc:
        dbt_start = doc.find(DBT_BLOCK_START_KEY)
        dbt_end = doc.find("```", dbt_start + len(DBT_BLOCK_START_KEY))

        if dbt_start > -1:
            dbt_block = doc[dbt_start + len(DBT_BLOCK_START_KEY):dbt_end]
            dbt = yaml.load(dbt_block, Loader=yaml.FullLoader)
        doc = doc[0:dbt_start].strip()

    return doc, dbt



def _scan_models(models_dir):
    """ local method to extract informatinon from each model dir
    """
    if not os.path.isdir(models_dir):
        logger.warning("%s directory not found" % models_dir)
        return

    models_dirs = os.walk(models_dir)
    for cdir, dirs, files in models_dirs:
        # doc_blocks = OrderedDict()
        # dbt_blocks = OrderedDict()
        doc_blocks = {}
        dbt_blocks = []
        for fname in files:
            # Parse the table name from the SQL file name
            if fname[-3:] != "sql":
                logger.info("Skipping non-sql file: " + fname)
                continue
            tname = fname[0:-4] # remove .sql from filename
            a_doc, a_dbt= _read_blocks(os.path.join(cdir, fname))

            # update doc block
            if a_doc:
                doc_blocks[tname] = a_doc
                b = {}
                b["name"] = quoted(tname)
                b["description"] = quoted("{{ doc('%s') }}" % tname)

                _quote_dict(a_dbt)
                for key in (["columns","docs"]):
                    if key in a_dbt:
                        b[key] = a_dbt[key]
                dbt_blocks.append(b)

        # write to file
        _write_property_yml(cdir, dbt_blocks, "models")
        _write_doc_md(cdir, doc_blocks)

def _quote_dict(d):
    """ Scan a dict and quote string
    """
    if not d: return
    if not isinstance(d,dict): return
    for k,v in d.items():
        if isinstance(v,list):
            for i in v:
                _quote_dict(i)
        if isinstance(v,dict):
            _quote_dict(v)
        if isinstance(v,str):
            d[k] = quoted(v)

def _scan_macros(macros_dir):
    """ Scan macro folder and collect resource information

    There are both `macro` and `test` inside.
    """
    if not os.path.isdir(macros_dir):
        logger.warning("%s directory not found" % macros_dir)
        return

    macro_dirs = os.walk(macros_dir)
    for cdir, dirs, files in macro_dirs:
        doc_blocks = {}
        dbt_blocks = []
        for fname in files:
            # Parse the table name from the SQL file name
            if fname[-3:] != "sql":
                logger.info("Skipping non-sql file: " + fname)
                continue

            with open(os.path.join(cdir, fname), 'r') as f:
                sql = f.read()

            # split into macro/test blocks
            # using a simple rule, need to be enhanced
            r = re.findall('(/\*.*?\*/.*? (?:macro|test|materialization) .*?end(?:macro|test|materialization) )', sql, re.DOTALL)
            for block in r:
                rr =  re.match('/\*.*?\*/.*? (macro|test|materialization) ([^ ]*?)(?:\(|, *adapter *= *(.*?) )', block, re.DOTALL)
                # print(block)
                # print("====")
                keyword = rr.group(1).strip()
                tname = rr.group(2).strip()
                if rr.group(3):
                    connector = rr.group(3).strip("\ \' \"")
                else:
                    connector = ""

                doc_start = block.find("/*")
                doc_end = block.find("*/")
                a_doc = block[doc_start + 2:doc_end] if doc_start > -1 else ""

                a_dbt = {}
                if a_doc:
                    dbt_start = a_doc.find(DBT_BLOCK_START_KEY)
                    dbt_end = a_doc.find("```", dbt_start + len(DBT_BLOCK_START_KEY))

                    if dbt_start > -1:
                        dbt_block = a_doc[dbt_start + len(DBT_BLOCK_START_KEY):dbt_end]
                        a_dbt = yaml.load(dbt_block, Loader=yaml.FullLoader)
                    a_doc = a_doc[0:dbt_start].strip()

                b = {}
                if keyword == "materialization":
                    b["name"] = quoted("materialization_" + tname + "_" + connector)
                elif keyword == "test":
                    b["name"] = quoted("test_" + tname)
                elif keyword == "macro":
                    b["name"] = quoted(tname)

                # document block
                if a_doc:
                    doc_blocks[tname] = a_doc
                    b["description"] = quoted("{{ doc('%s') }}" % tname)

                # dbt yml block
                if a_dbt:
                    _quote_dict(a_dbt)
                    for key in (["arguments","docs"]):
                        if key in a_dbt:
                            b[key] = a_dbt[key]

                dbt_blocks.append(b)

        # write to file
        _write_property_yml(cdir, dbt_blocks, "macros")
        _write_doc_md(cdir, doc_blocks)



def _write_property_yml(resource_dir, dbt_blocks, keyword="models"):
    """ write to property file, default is dbt_schema.yaml
        keyword is `models` or `macros`
    """
    if args.schema:
        property_file = args.schema
    else:
        property_file = os.path.join(args.dbt_dir, resource_dir, SCHEMA_FILE)

    if args.backup and os.path.isfile(property_file):
        os.rename(property_file, property_file[:len(property_file) - 4] + "_" +
                  datetime.datetime.now().isoformat().replace(":", "-") +
                  ".yml_")

    with open(property_file, "w") as f:
        f.write("""# This file was auto-generated by dbtdocstr.
# Don't manually update.
---
""")
        if not dbt_blocks:
            return
        f.write(f"version: 2\n{keyword}:\n")
        f.write(indent(yaml.dump(dbt_blocks, Dumper=Dumper, allow_unicode=True, sort_keys=False), " " * 2) )


def _write_doc_md(resource_dir, doc_blocks):
    """ write to doc file, default is docs.md
    """
    if args.doc:
        doc_file = args.doc
    else:
        doc_file = os.path.join(args.dbt_dir, resource_dir, DOC_FILE)

    if args.backup and os.path.isfile(doc_file):
        os.rename(doc_file, doc_file[:len(doc_file) - 3] + "_" +
                  datetime.datetime.now().isoformat().replace(":", "-") +
                  ".md_")

    with open(doc_file, "w") as f:
        f.write("""# This file was auto-generated by dbtdocstr.
# Don't manually update.
""")
        if not doc_blocks:
            return
        for key in doc_blocks:
            f.write("{%% docs %s %%}\n" % key)
            f.write(doc_blocks[key] + "\n")
            f.write("{% enddocs %}\n\n")


def _run():
    dbt_dir = args.dbt_dir
    models_dirs, macro_dirs = _get_dirs(dbt_dir)

    for models_dir in models_dirs:
        _scan_models(os.path.join(dbt_dir, models_dir))

    for macro_dir in macro_dirs:
        _scan_macros(os.path.join(dbt_dir, macro_dir))


args = {}
def read_conf():
    """ Read configuration from .dbtdoc if exits
    """
    # FOLDER = os.path.dirname(__file__)
    # try to get config file in current folder
    FOLDER = os.path.abspath(os.getcwd())
    CONFIG_FILE = FOLDER + "/" + ".dbtdoc"
    if not os.path.exists(CONFIG_FILE):
        # print("config file not found")
        return
    config = {}
    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f)

    if not config:
        return

    if "schema_file" in config:
        SCHEMA_FILE = config["schema_file"]
    if "doc_file" in config:
        DOC_FILE = config["doc_file"]
    if "quote_string" in config:
        QUOTE_STRING = config["quote_string"]

    # debug
    # print(f"SCHEMA_FILE={SCHEMA_FILE}")
    # print(f"DOC_FILE={DOC_FILE}")
    # print(f"QUOTE_STRING={QUOTE_STRING}")

    if QUOTE_STRING:
        yaml.add_representer(quoted, _represent_quoted)
    else:
        yaml.add_representer(quoted, _represent_str)

def main():
    global args
    """
    Entry point
    """
    ### config
    read_conf()

    parser = argparse.ArgumentParser(COMMAND)

    parser.add_argument(
        "dbt_dir",
        type=str,
        help="dbt root directory")
    parser.add_argument(
        "-b",
        "--backup",
        action="store_true",
        help="When set, take a back up of existing schema.yml and docs.md")
    parser.add_argument(
        "-d","--doc",
        type=str,
        help="output doc file"
    )
    parser.add_argument(
        "-s","--schema",
        type=str,
        help="output schema file"
    )

    args = parser.parse_args()
    _run()


if __name__ == "__main__":
    main()

