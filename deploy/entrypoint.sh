#!/bin/sh
set -eu
umask 027
exec "$@"
