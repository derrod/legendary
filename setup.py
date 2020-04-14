# !/usr/bin/env python
# coding: utf-8

import os
import sys

from setuptools import setup

from legendary import __version__ as legendary_version

if sys.version_info < (3, 8):
    sys.exit('python 3.8 or higher is required for legendary')

setup(
    name='legendary-gl',
    version=legendary_version,
    license='GPL-3',
    author='Rodney',
    author_email='rodney@rodney.io',
    packages=[
        'legendary',
        'legendary.api',
        'legendary.downloader',
        'legendary.lfs',
        'legendary.models',
    ],
    entry_points=dict(
        console_scripts=['legendary = legendary.cli:main']
    ),
    install_requires=[
        'requests'
    ],
    url='https://github.com/derrod/legendary',
    description='Free and open-source replacement for the Epic Game Launcher application.',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9'
        'Operating System :: Linux',
        'Operating System :: Microsoft',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Games/Entertainment',
        'Development Status :: 3 - Alpha',
    ],
)
