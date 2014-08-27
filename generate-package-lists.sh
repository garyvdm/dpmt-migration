#!/bin/sh

set -eufx

svn ls svn+ssh://svn.debian.org/svn/python-modules/packages/ | cut -d/ -f1 > dpmt-packages
svn ls svn+ssh://svn.debian.org/svn/python-apps/packages/ | cut -d/ -f1 > papt-packages
