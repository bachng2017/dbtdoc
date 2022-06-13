#!/usr/bin/env python3
import argparse, datetime, logging, os, sys, glob
from collections import defaultdict

from textwrap import indent
import yaml,re,os.path

LOGGER = logging.getLogger(__name__)

COMMAND = "dbtdoc"
DBT_BLOCK_START_KEY = "```dbt"

# default configuration
SCHEMA_FILE = "dbt_schema.yml"
DOC_FILE = "docs.md"
QUOTE_STRING = True

from logging import getLogger, StreamHandler, Formatter
LOGGER = getLogger(__name__)
LOGGER.setLevel(logging.ERROR) # only display errors
stream_handler = StreamHandler()
stream_handler.setLevel(logging.DEBUG)
handler_format = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(handler_format)
LOGGER.addHandler(stream_handler)


class Dumper(yaml.Dumper):
    """ A workaround to indent list more friendly
        See https://github.com/yaml/pyyaml/issues/234 for details
    """
    def increase_indent(self, flow=False, *ARGS, **kwARGS):
        return super().increase_indent(flow=flow, indentless=False)

class quoted(str):
    """ a dummy class mark an item that need to be quoted
    """
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
    """ Return the value of `model-paths` and `macro-path`from dbt_project.yml
    """
    dbt_project_file = os.path.join(dbt_dir, "dbt_project.yml")
    if not os.path.isfile(dbt_project_file):
        LOGGER.warning(f"dbt_project.yml not found in {dbt_dir}")
        return [dbt_dir]

    with open(dbt_project_file, "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    return config["model-paths"] + config["macro-paths"]


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


def _quote_item(d):
    """ Scan an item and quote string if it is necessary
    """
    if d is None:
        return None

    if isinstance(d, str):
        return quoted(d)

    if isinstance(d, dict):
        for k,v in d.items():
            d[k] = _quote_item(v)
        return d

    if isinstance(d,list):
        return list(map(lambda n: _quote_item(n), d))

    return d


def _scan_comment(target_dir):
    """ Scan comment in  sql files

    There are both `macro` and `test` inside.
    A macro file could have multi macro inside
    """
    LOGGER.info(f"Scan folder {target_dir} for macros")
    if not os.path.isdir(target_dir):
        LOGGER.warning("%s directory not found" % target_dir)
        return

    target_dirs = os.walk(target_dir)
    for cdir, dirs, files in target_dirs:
        doc_blocks = {}
        dbt_blocks = []
        top_level = 'unknown'
        for fname in files:
            # Parse the table name from the SQL file name
            if fname[-3:] != "sql":
                LOGGER.info("Skipping non-sql file: " + fname)
                continue

            with open(os.path.join(cdir, fname), 'r') as f:
                sql = f.read()

            # split into macro/test blocks
            # using a simple rule, need to be enhanced
            r = re.findall('(/\*.*?\*/.*? (?:macro|test|materialization) .*?end(?:macro|test|materialization) )', sql, re.DOTALL)
            if len(r) == 0: # this is model file
                a_doc = None
                a_dbt = {}
                top_level = 'models'
                pattern1 = '.*/\\*(.*?)```dbt(.*?)```.*\\*/'
                pattern2 = '.*/\\*(.*?)\\*/'
                rr = re.match(f"{pattern1}|{pattern2}", sql, re.DOTALL)
                if rr and rr.group(3): # only pattern2
                    a_doc = rr.group(3).strip()
                    d_dbt = {}
                elif rr:
                    a_doc = rr.group(1).strip()
                    a_dbt = yaml.load(rr.group(2).strip(), Loader=yaml.FullLoader)
                else:
                    a_doc = None
                    a_dbt = {}

                tname = fname[0:-4] # remove .sql from filename
                # update doc block
                if a_doc:
                    doc_blocks[tname] = a_doc
                    b = {}
                    b["name"] = quoted(tname)
                    b["description"] = quoted("{{ doc('%s') }}" % tname)

                    if a_dbt:
                        for key in (["columns","docs"]):
                            if key in a_dbt:
                                b[key] =_quote_item(a_dbt[key])

                    dbt_blocks.append(b)
            else:
                top_level = 'macros'
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
                        a_dbt = _quote_item(a_dbt)
                        for key in (["arguments","docs"]):
                            if key in a_dbt:
                                b[key] = a_dbt[key]

                    dbt_blocks.append(b)

        # write to file
        _write_property_yml(cdir, dbt_blocks, top_level)
        _write_doc_md(cdir, doc_blocks)

        # only do once
        if ARGS.only: break


def _write_property_yml(resource_dir, dbt_blocks, keyword="models"):
    """ write to property file, default is dbt_schema.yaml
        keyword is `models` or `macros`
    """
    if ARGS.schema:
        property_file = ARGS.schema
    else:
        property_file = os.path.join(resource_dir, SCHEMA_FILE)

    if ARGS.backup and os.path.isfile(property_file):
        os.rename(property_file, property_file[:len(property_file) - 4] + "_" +
                  datetime.datetime.now().isoformat().replace(":", "-") +
                  ".yml_")

    if not dbt_blocks:
        LOGGER.info(f"There is no properties to write to {property_file}")
        return
    LOGGER.info(f"Write out property file: {property_file}")

    with open(property_file, "w") as f:
        f.write("""# This file was auto-generated by dbtdocstr.
# Don't manually update.
---
""")
        f.write(f"version: 2\n{keyword}:\n")
        f.write(indent(yaml.dump(dbt_blocks, Dumper=Dumper, allow_unicode=True, sort_keys=False), " " * 2) )
    print(f"Wrote file {property_file}")


def _write_doc_md(resource_dir, doc_blocks):
    """ write to doc file, default is docs.md
    """
    if ARGS.doc:
        doc_file = ARGS.doc
    else:
        doc_file = os.path.join(resource_dir, DOC_FILE)

    if ARGS.backup and os.path.isfile(doc_file):
        os.rename(doc_file, doc_file[:len(doc_file) - 3] + "_" +
                  datetime.datetime.now().isoformat().replace(":", "-") +
                  ".md_")

    if not doc_blocks:
        LOGGER.info(f"There is no document to write to {doc_file}")
        return
    LOGGER.info(f"Write out doc file: {doc_file}")

    with open(doc_file, "w") as f:
        f.write("""# This file was auto-generated by dbtdocstr.
# Don't manually update.
""")
        for key in doc_blocks:
            f.write("{%% docs %s %%}\n" % key)
            f.write(doc_blocks[key] + "\n")
            f.write("{% enddocs %}\n\n")
    print(f"Wrote file {doc_file}")


def read_conf():
    """ Read configuration from .dbtdoc if exits
    """
    global SCHEMA_FILE, DOC_FILE, QUOTE_STRING
    # try to get config file in current folder
    folder = os.path.abspath(os.getcwd())
    config_file = folder + "/" + ".dbtdoc"
    if os.path.exists(config_file):
        config = {}
        with open(config_file, "r") as f:
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


def _clean(target_folder):
    """ Deleted dbtdoc file in `target_folder`
    """
    walk = os.walk(target_folder)
    for cdir, _, files in walk:
        delete_flag = False
        for item in [SCHEMA_FILE, DOC_FILE] :
            file_path = os.path.join(cdir, item)
            if os.path.exists(file_path):
                os.remove(file_path)
                delete_flag = True
        if delete_flag:
            print(f"Removed dbtdoc files in {cdir}")


def _run():
    dbt_dir = ARGS.dbt_dir
    print(f"Run {COMMAND} in {dbt_dir}")

    if ARGS.clear:
        _clean(dbt_dir)
    else:
        dirs = _get_dirs(dbt_dir)
        LOGGER.info(dirs)
        for d in dirs:
            # _scan_models(d)
            # _scan_macros(d)
            _scan_comment(d)


ARGS = {}
def main():
    global ARGS
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
        help="output doc filename"
    )
    parser.add_argument(
        "-o","--only",
        action="store_true",
        help="only process target folder only"
    )
    parser.add_argument(
        "-s","--schema",
        type=str,
        help="output schema filename"
    )
    parser.add_argument(
        "-c","--clear",
        action="store_true",
        help="cleanup dbtdoc files"
    )
    parser.add_argument(
        "-D","--debug",
        type=str,
        help="debug level: DEBUG/INFO/WARN/ERROR. Default is ERROR"
    )

    ARGS = parser.parse_args()
    if ARGS.debug:
        LOGGER.setLevel(getattr(logging, ARGS.debug))
    _run()


if __name__ == "__main__":
    main()

