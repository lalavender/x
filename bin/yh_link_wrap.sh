#!/bin/bash
echo "CALL $*" >> /tmp/yhlink_calls.log
exec /Users/lavender/Documents/x/yh_link "$@"
