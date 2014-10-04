#!/bin/sh

set -eufx

IMPORT_DSCS=~/git/debian/import-dscs/import-dscs.py
LIST=~/git/debian/dpmt-migration/packages

cache=$(pwd)/cache
mkdir -p $cache || true

rm -rf testmigration
mkdir testmigration
cd testmigration

for package in $(cat $LIST); do
	git init $package
	(
		cd $package
		git config user.name 'SVN-GIT migration'
		git config user.email python-modules-team@lists.alioth.debian.org
		$IMPORT_DSCS -c $cache $package
	)
done
