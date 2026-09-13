import pytest

def _alarm(cloudwatch, name):
    found = cloudwatch.describe_alarms(AlarmNames=[name])["MetricAlarms"]
    assert found, f"alarm {name} does not exist"
    return found[0]

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
    assert alarm["StateValue"] == "ALARM", (
        "alarm should already be in ALARM: no datapoints have been published "
        "and missing data is treated as breaching"
    )
