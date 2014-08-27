#!/bin/sh

set -eufx

RELEASES="oldstable stable testing unstable"

for release in $RELEASES; do
	chdist apt-get $release update
	xargs -L 1 chdist apt-get $release source --download-only --quiet < packages
done
