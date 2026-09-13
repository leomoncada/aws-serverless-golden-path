import json

def _alarm(cloudwatch, name):
    found = cloudwatch.describe_alarms(AlarmNames=[name])["MetricAlarms"]
    assert found, f"alarm {name} does not exist"
    return found[0]

def _recent_datapoints(alarm):
    """The datapoints CloudWatch used for this alarm's last evaluation."""
    return json.loads(alarm.get("StateReasonData") or "{}").get("recentDatapoints", [])

def test_error_alarm_exists_and_notifies_the_topic(cloudwatch, tf_outputs):
    alarm = _alarm(cloudwatch, "{{cookiecutter.service_name}}-lambda-errors")
    assert alarm["MetricName"] == "Errors"
    assert tf_outputs["alarm_topic_arn"] in alarm["AlarmActions"]

def test_dlq_alarm_watches_visible_messages(cloudwatch, tf_outputs):
    alarm = _alarm(cloudwatch, "{{cookiecutter.service_name}}-dlq-not-empty")
    assert alarm["MetricName"] == "ApproximateNumberOfMessagesVisible"

# The point of the whole task. An alarm that cannot fire when its metric stops
# being published is decorative, and that is the CloudWatch default.
def test_absence_of_signal_alarm_fires_with_no_data(cloudwatch):
    alarm = _alarm(cloudwatch, "{{cookiecutter.service_name}}-no-invocations")
    assert alarm["TreatMissingData"] == "breaching"

    # INSUFFICIENT_DATA is the state this alarm exists to rule out. It is where
    # the CloudWatch default parks an alarm during exactly the outage that stops
    # the metric being published, and nothing pages from there.
    assert alarm["StateValue"] != "INSUFFICIENT_DATA", (
        "missing data is treated as breaching, so this alarm must never sit in "
        "INSUFFICIENT_DATA"
    )

    # The firing assertion below only means anything while the alarm's
    # evaluation window is genuinely empty, and the integration tests in this
    # suite invoke the processor. This used to skip when it found datapoints:
    # loud in the log, but a skip exits 0, so the one assertion this service's
    # observability claim rests on could be quietly absent from a green CI
    # run, and nothing enforced the collection order that kept it present.
    # An empty window is a precondition of the assertion, so it is asserted,
    # not skipped.
    #
    # `make test` runs this file first, in its own pytest session, before
    # anything invokes the function, and `make ci` runs `make test` against a
    # freshly applied stack. The window is therefore empty by construction in
    # both supported flows. If it is not, something invoked the processor
    # first, and that is worth a red build rather than a green one that
    # proved nothing.
    recent = _recent_datapoints(alarm)
    assert not recent, (
        f"the processor was invoked inside the alarm's evaluation window "
        f"(recentDatapoints={recent}), so the absence of signal this test "
        f"exists to prove cannot be observed. This test has to run before "
        f"anything invokes the function; `make test` runs it first, in its "
        f"own session. Rerun after a fresh `make apply`, or once the alarm's "
        f"five minute period has passed with no invocations."
    )

    assert alarm["StateValue"] == "ALARM", (
        "alarm should already be in ALARM: no datapoints have been published "
        "and missing data is treated as breaching"
    )
