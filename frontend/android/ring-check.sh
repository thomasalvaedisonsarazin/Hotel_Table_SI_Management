#!/bin/sh
# Runs the ring tests on the emulator. Failures become annotations on the GitHub run page.
./gradlew --no-daemon connectedDebugAndroidTest > ring-check.log 2>&1
code=$?
tail -n 40 ring-check.log
if [ "$code" -ne 0 ]; then
  grep -hoE 'message="[^"]{1,300}' app/build/outputs/androidTest-results/connected/debug/*.xml 2>/dev/null \
    | head -n 5 | while IFS= read -r line; do echo "::error title=Ring test::$line"; done
  grep -E 'What went wrong|FAILED|No connected devices|Exception|error:' -A1 ring-check.log \
    | head -n 5 | while IFS= read -r line; do echo "::error title=Gradle::$line"; done
fi
exit "$code"
