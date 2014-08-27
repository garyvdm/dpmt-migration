#!/bin/sh

set -eufx

RELEASES="oldstable stable testing unstable"

while read package; do
	git init $package
	(
		cd $package
		for release in $RELEASES; do
			dsc=$(chdist apt-cache $release showsrc $package | sed -nre 's/^ .* ([^ ]*\.dsc)$/\1/ p' | head -n 1)
			git-import-dsc ../../sources/$dsc
		done
	)
done < packages
