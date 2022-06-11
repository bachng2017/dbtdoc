#!/usr/bin/env python
from setuptools import setup
from codecs import open
from os import path

VERSION = "0.0.7"

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup (
    name='dbtdoc',
    packages=['dbtdoc'],
    version=VERSION,
    license='Apache',
    install_requires=[
        "setuptools>=40.3.0",
    ],
    author='bachng',
    author_email='bachng@gmail.com',
    url='https://github.com/bachng2017/dbtdoc',
    description='Document tool for dbt',
    long_description=long_description,
    long_description_content_type='text/markdown',
    keywords='dbt doc sql',
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        'Programming Language :: Python :: 3.8',
    ],
    entry_points = {
        'console_scripts': ['dbtdoc = dbtdoc.dbtdoc:main'] },
    python_requires='>=3.8',
)
