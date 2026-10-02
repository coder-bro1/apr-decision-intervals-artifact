#!/bin/bash
# E3 (ADDENDUM_V4_E3_HUMANEVAL.md): compile and test every variant of one HumanEval-Java bug, two repetitions.
# /inputs/bug = bug name, /inputs/variants/<v>/<BUG>.java = fixed, buggy and candidate files. Evidence -> /output/res.
set -u
B=$(cat /inputs/bug)
CP=/bench/lib/junit4-4.12.jar:/bench/lib/hamcrest-all-1.3.jar
R=/output/res
mkdir -p "$R" /tmp/base
cp -r /bench/src/main/java /tmp/base/java
cp /bench/src/test/java/humaneval/TEST_$B.java /tmp/base/TEST_$B.java
java -version > "$R/java_version.txt" 2>&1
for rep in 1 2; do
  for v in $(ls /inputs/variants); do
    [ -f "$R/$v.$rep.done" ] && continue
    w=/tmp/w; rm -rf $w; mkdir -p $w/out
    cp -r /tmp/base/java $w/src
    cp "/inputs/variants/$v/$B.java" "$w/src/humaneval/buggy/$B.java"
    timeout 300 javac -nowarn -encoding UTF-8 -cp "$CP" -sourcepath $w/src -d $w/out \
      "$w/src/humaneval/buggy/$B.java" /tmp/base/TEST_$B.java > "$R/$v.$rep.javac.txt" 2>&1
    echo $? > "$R/$v.$rep.javac.rc"
    if [ "$(cat "$R/$v.$rep.javac.rc")" = "0" ]; then
      (cd $w && timeout 300 java -Xmx256m -cp "$w/out:$CP" org.junit.runner.JUnitCore humaneval.TEST_$B > "$R/$v.$rep.junit.txt" 2>&1)
      echo $? > "$R/$v.$rep.junit.rc"
    fi
    touch "$R/$v.$rep.done"
  done
done
echo done > "$R/ALLDONE"
