# !/usr/bin/env python
# coding: utf-8

import os
import sys

from setuptools import setup
from build_manpages.build_manpages import build_manpages, get_build_py_cmd, get_install_cmd
from setuptools.command.build_py import build_py
from setuptools.command.install import install

from legendary import __version__ as legendary_version

if sys.version_info < (3, 8):
    sys.exit('python 3.8 or higher is required for legendary')

with open("README.md", "r") as fh:
    long_description_l = fh.readlines()
    del long_description_l[2:5]  # remove discord/twitter link and logo
    long_description = ''.join(long_description_l)

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
        'legendary.utils',
    ],
    entry_points=dict(
        console_scripts=['legendary = legendary.cli:main']
    ),
    install_requires=[
        'requests<3.0',
        'setuptools',
        'wheel',
        'argparse-manpage'
    ],
    url='https://github.com/derrod/legendary',
    description='Free and open-source replacement for the Epic Games Launcher application',
    long_description=long_description,
    long_description_content_type="text/markdown",
    python_requires='>=3.8',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Operating System :: POSIX :: Linux',
        'Operating System :: Microsoft',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Games/Entertainment',
        'Development Status :: 4 - Beta',
    ],
    cmdclass={
        'build_manpages': build_manpages,
        # Re-define build_py and install commands so the manual pages
        # are automatically re-generated and installed (optional)
        'build_py': get_build_py_cmd(build_py),
        'install': get_install_cmd(install),
    },
)
