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

    # With nothing in the evaluation window the alarm has to be firing. Whether
    # the window is empty is read from the alarm's own last evaluation rather
    # than assumed: the integration tests invoke the processor, so a second run
    # of the suite inside the alarm's five minute period sees real datapoints
    # and a correctly quiet alarm.
    if not _recent_datapoints(alarm):
        assert alarm["StateValue"] == "ALARM", (
            "alarm should already be in ALARM: no datapoints have been published "
            "and missing data is treated as breaching"
        )
