#!/bin/sh
#
# Copyright (C) 2021, Sebastian Nagel.
#
# This file is part of the module 'gapiannotator' and is released under
# the MIT License: https://opensource.org/licenses/MIT
#
INSTALL=
for P in python-all-dev libexiv2-dev libboost-python-dev g++ libturbojpeg0-dev; do
    if ! dpkg -l $P >/dev/null 2>&1; then
        INSTALL="$INSTALL $P"
    fi
done
if [ -n "$INSTALL" ]; then
    echo "It seems some packages are missing, or dpkg not found:$INSTALL\n"
    exit 1
fi
echo "All requirements met."
exit 0