# -*- coding: utf-8 -*-
#
# Copyright (C) 2021, Sebastian Nagel.
#
# This file is part of the module 'gapiannotator' and is released under
# the MIT License: https://opensource.org/licenses/MIT
#
import os
import sys
import subprocess
import warnings

from setuptools import find_packages, setup

DEPENDENCIES = [
    "py3exiv2",
    "Pillow",
    "inotifyrecursive",
    "google-cloud-vision",
    "google-cloud-translate",
    "googlemaps",
    "webcolors",
    "cffi",
    "jpegtran-cffi",
    "aiohttp",
    "asyncio",
    "libsass"
]
EXCLUDE_FROM_PACKAGES = []
ROOT = sys.path[0]

# check requirements
res=subprocess.run(["sh",os.path.join(ROOT,"check_requirements.sh")],capture_output=True)
if not res.returncode == 0:
    warnings.warn(res.stdout.decode('utf-8'),Warning)

# Compile sqlite-hexhammdist
res=subprocess.run(["make", "-C", os.path.join(ROOT, "gapiannotator","sqlite-hexhammdist")], capture_output=True)
if not res.returncode == 0:
    warnings.warn(res.stdout.decode('utf-8'),Warning)

# load README
with open(os.path.join(ROOT, "README.md")) as file:
    README = file.read()

setup(
    name="gapi-annotator",
    version="0.1.0",
    author="Sebastian Nagel",
    author_email="snagel86@gmail.com",
    description="",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/nagel86/gapi-annotator",
    project_urls={
        "Bug Tracker": "https://github.com/nagel86/gapi-annotator/issues",
    },
    packages=find_packages(exclude=EXCLUDE_FROM_PACKAGES),
    package_data={'gapiannotator.web-templates': ['*'],'gapiannotator.web': ['*'],'gapiannotator': ['sqlite-hexhammdist/sqlite-hexhammdist.so']},
    include_package_data=True,
    keywords=[],
    scripts=[],
    entry_points="""
        [console_scripts]
        gapi-annotator=gapiannotator:webgui
        gapi-annotator-cli=gapiannotator:cli
    """,
    zip_safe=False,
    install_requires=DEPENDENCIES,
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux", # only tested on linux
    ],
)