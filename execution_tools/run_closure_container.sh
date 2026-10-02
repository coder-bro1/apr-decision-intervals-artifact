#!/bin/sh
set -eu
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=America/Los_Angeles
export JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8
variant="$1"
case "$variant" in fixed|buggy|candidate) ;; *) exit 64 ;; esac
mkdir /tmp/project
cp -R /source/. /tmp/project/
cp "/variants/$variant.java" /tmp/project/src/com/google/javascript/jscomp/PeepholeFoldConstants.java
cd /tmp/project
java -version
# The historic build defaults to Java 6, which the installed JDK 11 cannot target.
# Identical source/target overrides are applied to every variant, without source edits.
java -cp '/ant/*' org.apache.tools.ant.Main \
    -Dant.build.javac.source=7 -Dant.build.javac.target=7 compile-tests
javac -cp 'lib/junit.jar:build/classes:build/test' -d build/test /runner/RunClosureTests.java
printf 'PILOT_BUILD_OK\n'
set +e
java -cp 'lib/*:build/classes:build/test' RunClosureTests trigger
trigger_exit=$?
java -cp 'lib/*:build/classes:build/test' RunClosureTests class
class_exit=$?
set -e
printf 'PILOT_EXITS trigger=%s class=%s\n' "$trigger_exit" "$class_exit"
# Expected test failures are evidence, not an infrastructure failure.
exit 0
